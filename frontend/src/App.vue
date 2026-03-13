<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import Sidebar from './components/Sidebar.vue'
import MainInput from './components/MainInput.vue'
import { useChatHistory } from './composables/useChatHistory'

const { sessions, activeChatId, loadSessions, createNewChat, refreshSession } = useChatHistory()

// ─── WebSocket ─────────────────────────────────────────────────────────────
const ws = ref<WebSocket | null>(null)
const isConnected = ref(false)

function connectWs(sessionId: string) {
  if (ws.value) {
    ws.value.onclose = null  // prevent auto-reconnect on intentional close
    ws.value.close()
  }

  const socket = new WebSocket(`ws://localhost:8000/ws/agent?session_id=${sessionId}`)
  ws.value = socket

  socket.onopen = () => {
    isConnected.value = true
  }

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data)
    // If server echoes back a session_id (on connection), sync it
    if (data.session_id && data.session_id !== activeChatId.value) {
      activeChatId.value = data.session_id
    }
    pushMessage(data)
  }

  socket.onclose = () => {
    isConnected.value = false
    // Re-connect after 3s
    setTimeout(() => {
      if (activeChatId.value) connectWs(activeChatId.value)
    }, 3000)
  }
}

// ─── Messages for current session ─────────────────────────────────────────
const messages = ref<any[]>([])
const hasStarted = ref(false)
const scrollContainer = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

watch(messages, scrollToBottom, { deep: true })

function pushMessage(data: any) {
  messages.value.push(data)
  // Update sidebar preview after agent/user messages
  if (activeChatId.value && (data.type === 'info' || data.type === 'user')) {
    const preview = (data.message || '').slice(0, 80)
    refreshSession(activeChatId.value, { preview })
  }
}

// ─── Session switching ─────────────────────────────────────────────────────
const { loadMessages } = useChatHistory()

async function switchToSession(id: string) {
  activeChatId.value = id
  messages.value = []
  hasStarted.value = false

  // Load existing messages from backend
  const hist = await loadMessages(id)
  if (hist.length > 0) {
    hasStarted.value = true
    messages.value = hist.map(m => ({
      type: m.role === 'user' ? 'user' : 'info',
      message: m.content,
      images: m.images ?? [],
    }))
  }

  connectWs(id)
}

// ─── New chat ──────────────────────────────────────────────────────────────
async function handleNewChat() {
  // createNewChat already called in Sidebar → we just switch to the new active session
  messages.value = []
  hasStarted.value = false
  if (activeChatId.value) {
    connectWs(activeChatId.value)
  }
}

// ─── User submit ───────────────────────────────────────────────────────────
function handleUserSubmit(payload: { text: string; images: string[] }) {
  const { text, images } = payload
  hasStarted.value = true
  pushMessage({ type: 'user', message: text, images })
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'user_input', message: text, images }))
  }
  // Update title of session in sidebar to first message
  const sid = activeChatId.value
  const session = sessions.value.find(s => s.id === sid)
  if (sid && session && (!session.title || session.title === 'New Chat')) {
    refreshSession(sid, { title: (text || '📷 Image').slice(0, 40) })
  }
}

function resumeAgent() {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'resume' }))
    pushMessage({ type: 'info', message: '已发送继续执行指令。' })
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadSessions()
  if (sessions.value.length > 0 && sessions.value[0]) {
    await switchToSession(sessions.value[0].id)
  } else {
    const session = await createNewChat()
    connectWs(session.id)
  }
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.onclose = null
    ws.value.close()
  }
})
</script>

<template>
  <div class="h-screen w-full flex bg-[#FDFBF7] font-sans selection:bg-neutral-200">
    <Sidebar
      @new-chat="handleNewChat"
      @select-chat="switchToSession"
    />
    
    <!-- Main content: offset by sidebar icon rail (w-16 = 64px) -->
    <main class="flex-1 flex flex-col relative h-full" style="margin-left: 64px">
      <!-- Top nav indicator -->
      <header class="absolute top-0 left-0 w-full p-6 flex justify-end z-10 pointer-events-none">
        <div class="flex items-center gap-2 bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-200/50 shadow-sm">
          <div class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-green-500' : 'bg-red-500'"></div>
          <span class="text-xs font-medium text-neutral-600">{{ isConnected ? $t('common.agent_ready') : $t('common.connecting') }}</span>
        </div>
      </header>
      
      <div v-if="!hasStarted" class="flex-1 overflow-hidden transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] opacity-100 translate-y-0">
        <MainInput @submit="handleUserSubmit" />
      </div>

      <div v-else class="flex-1 flex flex-col max-w-4xl mx-auto w-full pt-20 pb-6 px-4 min-h-0">
        <!-- Chat history stream -->
        <div ref="scrollContainer" class="flex-1 overflow-y-auto space-y-6 pb-20 custom-scrollbar pr-4">
          <div v-for="(msg, idx) in messages" :key="idx" 
               class="p-4 rounded-2xl max-w-[85%] animate-fade-in-up"
               :class="msg.type === 'user' ? 'bg-neutral-100 text-neutral-800 ml-auto rounded-tr-sm' : 'bg-white border border-neutral-100 shadow-sm mr-auto rounded-tl-sm'">
            
            <div v-if="msg.type === 'user'" class="flex flex-col gap-2">
              <!-- Attached images -->
              <div v-if="msg.images && msg.images.length > 0" class="flex flex-wrap gap-2">
                <img
                  v-for="(src, i) in msg.images"
                  :key="i"
                  :src="src"
                  class="max-h-48 max-w-xs rounded-xl object-cover border border-neutral-200/60 shadow-sm"
                  alt="attached image"
                />
              </div>
              <div v-if="msg.message" class="text-[15px] leading-relaxed">{{ msg.message }}</div>
            </div>
            
            <div v-else-if="msg.type === 'info'" class="flex gap-3">
              <div class="w-6 h-6 rounded-full bg-neutral-900 flex-shrink-0 flex items-center justify-center">
                <span class="text-white text-[10px] font-bold">AI</span>
              </div>
              <div class="text-[15px] leading-relaxed text-neutral-700 font-serif">
                {{ msg.type === 'info' && msg.message === 'Connected to NeoFish Agent WebSocket' ? $t('common.connected_ws') : (msg.message_key ? $t(msg.message_key, msg.params || {}) : msg.message) }}
              </div>
            </div>

            <div v-else-if="msg.type === 'image'" class="flex flex-col gap-3 w-full">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-neutral-900 flex-shrink-0 flex items-center justify-center">
                  <span class="text-white text-[10px] font-bold">AI</span>
                </div>
                <div class="text-[15px] leading-relaxed text-neutral-700 font-serif">{{ msg.description }}</div>
              </div>
              <div class="mt-1 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Screenshot" />
              </div>
            </div>

            <div v-else-if="msg.type === 'action_required'" class="flex flex-col gap-4 w-full">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-orange-500 flex-shrink-0 flex items-center justify-center shadow-sm">
                  <span class="text-white text-[12px] font-bold">!</span>
                </div>
                <div class="text-[15px] leading-relaxed text-neutral-800 font-medium pt-0.5">
                  {{ $t('common.action_required') }}：{{ msg.reason }}
                </div>
              </div>
              <div v-if="msg.image" class="mt-2 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Action Required" />
              </div>
              <button @click="resumeAgent" class="mt-3 px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-all self-start font-medium text-sm shadow-md active:scale-95">
                {{ $t('common.resume_button') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Sticky bottom input -->
        <div class="sticky bottom-0 pt-4 bg-gradient-to-t from-[#FDFBF7] pb-4 backdrop-blur-sm">
          <MainInput :minimal="true" @submit="handleUserSubmit" class="!my-0 !h-auto" />
        </div>
      </div>
    </main>
  </div>
</template>

<style>
.animate-fade-in-up {
  animation: fadeInUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0,0,0,0.1);
  border-radius: 10px;
}
</style>
