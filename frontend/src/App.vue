<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import Sidebar from './components/Sidebar.vue'
import MainInput from './components/MainInput.vue'
import BrowserView from './components/BrowserView.vue'
import ThinkingChain from './components/ThinkingChain.vue'
import { useChatHistory } from './composables/useChatHistory'
import { useDebugMode } from './composables/useDebugMode'
import { useThemeMode } from './composables/useThemeMode'

const { t } = useI18n()
const { sessions, activeChatId, loadSessions, createNewChat, refreshSession } = useChatHistory()
const { debugMode } = useDebugMode()
useThemeMode()

// ─── WebSocket ─────────────────────────────────────────────────────────────
const ws = ref<WebSocket | null>(null)
const isConnected = ref(false)
const isInTakeover = ref(false)
const isTaskRunning = ref(false)
const browserFrame = ref('')
const browserUrl = ref('')
const browserViewport = ref({ width: 1280, height: 800 })

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
    if (data.session_id && data.session_id !== activeChatId.value) {
      activeChatId.value = data.session_id
    }
    if (data.type === 'task_status') {
      isTaskRunning.value = data.status === 'running'
      return
    }
    if (data.message_key === 'common.agent_thinking' && !debugMode.value) {
      return
    }
    if (data.type === 'takeover_started') {
      isInTakeover.value = true
      browserFrame.value = data.image || ''
      browserUrl.value = data.url || ''
      browserViewport.value = data.viewport || { width: 1280, height: 800 }
    } else if (data.type === 'takeover_frame') {
      browserFrame.value = data.image || ''
      browserUrl.value = data.url || browserUrl.value
      return
    } else if (data.type === 'takeover_ended') {
      isInTakeover.value = false
      browserFrame.value = ''
    }
    if (data.message_key === 'common.agent_starting') {
      isTaskRunning.value = true
    }
    if (data.message_key === 'common.task_completed' || data.message_key === 'common.task_cancelled' || data.message_key === 'common.task_stopped') {
      isTaskRunning.value = false
    }
    pushMessage(data)
  }

  socket.onclose = () => {
    isConnected.value = false
    isInTakeover.value = false
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

/** Check if user is near the bottom of the scroll container */
function isNearBottom(): boolean {
  if (!scrollContainer.value) return true
  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
  // Consider "near bottom" if within 100px of the bottom
  return scrollTop + clientHeight >= scrollHeight - 100
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

/** Scroll to bottom only if user is already near the bottom */
function scrollToBottomIfNearBottom() {
  if (isNearBottom()) {
    scrollToBottom()
  }
}

watch(messages, scrollToBottomIfNearBottom, { deep: true })

function isThinkingMessage(msg: any): boolean {
  return msg.message_key === 'common.agent_thinking' || 
         (msg.message && msg.message.includes('thinking'))
}

function isToolCallMessage(msg: any): boolean {
  return msg.message_key === 'common.executing_action' || 
         (msg.message && msg.message.startsWith('Executing action:'))
}

function isHiddenMessage(msg: any): boolean {
  const hiddenKeys = ['common.connected_ws', 'common.context_compressing', 'common.manual_compressing', 'common.agent_resumed', 'common.sent_resume', 'common.message_queued', 'common.agent_thinking']
  if (hiddenKeys.includes(msg.message_key)) return true
  if (msg.message === 'Connected to NeoFish Agent WebSocket') return true
  if (msg.message && msg.message.includes('Context threshold reached')) return true
  if (msg.message && msg.message.includes('Manual compression')) return true
  if (msg.message && msg.message.includes('已发送继续执行')) return true
  return false
}

function getToolName(msg: any): string | null {
  if (msg.params?.tool) return msg.params.tool
  const match = msg.message?.match(/Executing action: `(\w+)`/)
  return match ? match[1] : null
}

function getToolDisplayName(toolName: string): string {
  const key = `tools.${toolName}`
  const translated = t(key)
  return translated === key ? t('tools.default') : translated
}

function translateMessageFallback(msg: string): { message_key?: string; params?: Record<string, any> } {
  if (msg === 'Agent is thinking...') {
    return { message_key: 'common.agent_thinking' }
  }
  if (msg === '[Takeover] Browser opened for manual interaction.') {
    return { message_key: 'common.takeover_browser_opened' }
  }
  if (msg.startsWith('[Takeover Ended] Resumed at:')) {
    const urlMatch = msg.match(/Resumed at: (.+)/)
    return { message_key: 'common.takeover_ended_message', params: { url: urlMatch ? urlMatch[1] : '' } }
  }
  if (msg.startsWith('[Action Required]')) {
    return { message_key: 'common.action_required_prefix' }
  }
  if (msg.startsWith('Agent starting task:')) {
    const task = msg.replace('Agent starting task: ', '')
    return { message_key: 'common.agent_starting', params: { task } }
  }
  if (msg === 'Agent paused for manual takeover. Waiting for you to finish…') {
    return { message_key: 'common.agent_paused_for_takeover' }
  }
  return {}
}

function renderMarkdown(text: string): string {
  return marked.parse(text) as string
}

interface ThinkingStep {
  type: 'thinking' | 'tool'
  content: string
  completed: boolean
}

interface ProcessedMessage {
  type: string
  message?: string
  message_key?: string
  params?: Record<string, any>
  images?: string[]
  files?: { name: string; data: string; type: string }[]
  image?: string
  description?: string
  reason?: string
  final_url?: string
  mime_type?: string
  data?: string
  filename?: string
  thinkingChain?: {
    steps: ThinkingStep[]
    isActive: boolean
  }
}

const processedMessages = computed(() => {
  if (debugMode.value) {
    return messages.value.map(msg => ({ ...msg }))
  }
  
  const result: ProcessedMessage[] = []
  let currentChain: { steps: ThinkingStep[]; startIdx: number } | null = null
  
  for (let i = 0; i < messages.value.length; i++) {
    const msg = messages.value[i]
    
    if (isHiddenMessage(msg)) continue
    
    if (isThinkingMessage(msg) || isToolCallMessage(msg)) {
      if (!currentChain) {
        currentChain = { steps: [], startIdx: i }
      }
      
      if (isThinkingMessage(msg)) {
        currentChain.steps.push({
          type: 'thinking',
          content: t('status.thinking'),
          completed: false
        })
      } else {
        currentChain.steps.push({
          type: 'tool',
          content: getToolDisplayName(getToolName(msg) || ''),
          completed: false
        })
        if (currentChain.steps.length > 1) {
          const prevStep = currentChain.steps[currentChain.steps.length - 2]
          if (prevStep) prevStep.completed = true
        }
      }
    } else {
      if (currentChain) {
        if (currentChain.steps.length > 0) {
          const lastStep = currentChain.steps[currentChain.steps.length - 1]
          if (lastStep) lastStep.completed = true
        }
        result.push({
          type: 'thinking_chain',
          thinkingChain: {
            steps: currentChain.steps,
            isActive: false
          }
        })
        currentChain = null
      }
      result.push({ ...msg })
    }
  }
  
  if (currentChain && currentChain.steps.length > 0) {
    result.push({
      type: 'thinking_chain',
      thinkingChain: {
        steps: currentChain.steps,
        isActive: true
      }
    })
  }
  
  return result
})

function pushMessage(data: any) {
  messages.value.push(data)
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
  isInTakeover.value = false
  browserFrame.value = ''

  // Load existing messages from backend
  const hist = await loadMessages(id)
  if (hist.length > 0) {
    hasStarted.value = true
    messages.value = hist.map(m => {
      // Check if this is an image message from agent
      if (m.role === 'assistant' && m.image_data) {
        if (m.content.startsWith('[Action Required]')) {
          return {
            type: 'action_required',
            reason: m.content.replace('[Action Required] ', ''),
            image: m.image_data
          }
        } else if (m.content.startsWith('[Image]')) {
          return {
            type: 'image',
            description: m.content.replace('[Image] ', ''),
            image: m.image_data
          }
        } else if (m.content.startsWith('[Takeover Ended]')) {
          const urlMatch = m.content.match(/Resumed at: (.+)/)
          return {
            type: 'takeover_ended',
            message: m.content.replace('[Takeover Ended] ', ''),
            message_key: 'common.takeover_ended_message',
            params: { url: urlMatch ? urlMatch[1] : '' },
            final_url: urlMatch ? urlMatch[1] : '',
            image: m.image_data
          }
        }
      }
      return {
        type: m.role === 'user' ? 'user' : 'info',
        message: m.content,
        message_key: m.message_key || translateMessageFallback(m.content).message_key,
        params: m.params || translateMessageFallback(m.content).params,
        images: m.images ?? [],
      }
    })
  }

  connectWs(id)
}

// ─── New chat ──────────────────────────────────────────────────────────────
async function handleNewChat() {
  // createNewChat already called in Sidebar → we just switch to the new active session
  messages.value = []
  hasStarted.value = false
  isInTakeover.value = false
  browserFrame.value = ''
  if (activeChatId.value) {
    connectWs(activeChatId.value)
  }
}

// ─── User submit ───────────────────────────────────────────────────────────
function handleUserSubmit(payload: { text: string; images: string[]; files: { name: string; data: string; type: string }[] }) {
  const { text, images, files } = payload
  hasStarted.value = true
  pushMessage({ type: 'user', message: text, images, files })
  // Always scroll to bottom when user sends a message
  scrollToBottom()
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'user_input', message: text, images, files }))
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

function stopTask() {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'stop_task' }))
    isTaskRunning.value = false
  }
}

/** Request an embedded browser takeover. */
function requestTakeover() {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'takeover' }))
  }
}

/** Signal that the user is finished with the embedded browser takeover. */
function signalTakeoverDone() {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'takeover_done' }))
  }
}

// ─── Embedded browser input forwarding ────────────────────────────────────

function onBrowserClick(payload: { x: number; y: number; button: string }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_click', ...payload }))
}

function onBrowserDblClick(payload: { x: number; y: number }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_double_click', ...payload }))
}

function onBrowserKey(payload: { key: string }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_key', ...payload }))
}

function onBrowserType(payload: { text: string }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_type', ...payload }))
}

function onBrowserScroll(payload: { deltaX: number; deltaY: number }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_scroll', ...payload }))
}

function onBrowserNavigate(payload: { url: string }) {
  ws.value?.send(JSON.stringify({ type: 'takeover_navigate', url: payload.url }))
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
  <div class="theme-app h-screen w-full flex overflow-hidden font-sans">
    <Sidebar
      @new-chat="handleNewChat"
      @select-chat="switchToSession"
    />
    
    <main class="relative flex h-full min-w-0 flex-1 flex-col">
      <!-- Top nav indicator -->
      <header class="absolute top-0 left-0 w-full p-6 flex justify-end gap-3 z-10 pointer-events-none">
        <!-- Agent status indicator + proactive takeover button -->
        <div class="theme-badge pointer-events-auto flex items-center gap-2 rounded-full px-3 py-1.5 backdrop-blur-md">
          <div class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-green-500' : 'bg-red-500'"></div>
          <span class="theme-text-secondary text-xs font-medium">{{ isConnected ? $t('common.agent_ready') : $t('common.connecting') }}</span>
          <!-- Proactive takeover button (only shown during an active chat when not already in takeover) -->
          <button
            v-if="isTaskRunning"
            @click="stopTask"
            class="ml-1 text-xs font-semibold text-red-600 hover:text-red-800 bg-red-50 hover:bg-red-100 px-2 py-0.5 rounded-full transition-colors"
          >{{ $t('common.stop_task') }}</button>
          <button
            v-if="hasStarted && isConnected && !isInTakeover"
            @click="requestTakeover"
            class="theme-button-soft ml-1 rounded-full px-2 py-0.5 text-xs font-semibold transition-colors"
            :title="$t('common.proactive_takeover')"
          >{{ $t('common.proactive_takeover') }}</button>
        </div>
      </header>
      
      <div v-if="!hasStarted" class="flex-1 overflow-hidden transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] opacity-100 translate-y-0">
        <MainInput @submit="handleUserSubmit" />
      </div>

      <div v-else class="flex-1 flex flex-col max-w-4xl mx-auto w-full pt-20 pb-6 px-4 min-h-0">
        <!-- Chat history stream -->
        <div ref="scrollContainer" class="theme-scrollbar flex-1 overflow-y-auto space-y-6 pb-20 pr-4">
          <div v-for="(msg, idx) in processedMessages" :key="idx" 
               class="max-w-[85%] animate-fade-in-up"
               :class="msg.type === 'user' ? 'theme-card-soft theme-text-primary ml-auto rounded-tr-sm p-4 rounded-2xl' : (msg.type === 'thinking_chain' ? 'mr-auto w-full' : 'theme-card mr-auto rounded-tl-sm p-4 rounded-2xl')">
            
            <!-- Thinking Chain -->
            <ThinkingChain 
              v-if="msg.type === 'thinking_chain'"
              :steps="msg.thinkingChain?.steps || []"
              :isActive="msg.thinkingChain?.isActive || false"
            />
            
            <!-- User message -->
            <div v-else-if="msg.type === 'user'" class="flex flex-col gap-2">
              <div v-if="msg.images && msg.images.length > 0" class="flex flex-wrap gap-2">
                <img
                  v-for="(src, i) in msg.images"
                  :key="i"
                  :src="src"
                  class="max-h-48 max-w-xs rounded-xl object-cover border border-neutral-200/60 shadow-sm"
                  alt="attached image"
                />
              </div>
              <div v-if="msg.files && msg.files.length > 0" class="flex flex-wrap gap-2">
                <div
                  v-for="(file, i) in msg.files"
                  :key="i"
                  class="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-neutral-200/60 shadow-sm"
                >
                  <span class="text-xs font-medium text-neutral-700 truncate max-w-32">{{ file.name }}</span>
                </div>
              </div>
              <div v-if="msg.message" class="text-[15px] leading-relaxed">{{ msg.message }}</div>
            </div>
            
            <!-- Info message (AI response) -->
            <div v-else-if="msg.type === 'info'" class="flex gap-3">
              <div class="theme-button-strong flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full">
                <span class="text-[10px] font-bold">AI</span>
              </div>
              <div 
                class="theme-prose text-[15px] leading-relaxed font-serif prose prose-sm max-w-none"
                v-html="renderMarkdown(msg.message_key ? $t(msg.message_key, msg.params || {}) : msg.message || '')"
              ></div>
            </div>

            <!-- Takeover started notification -->
            <div v-else-if="msg.type === 'takeover_started'" class="theme-card flex w-full flex-col gap-3 rounded-2xl rounded-tl-sm p-4">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-amber-500 flex-shrink-0 flex items-center justify-center shadow-sm">
                  <span class="text-white text-[11px] font-bold">↗</span>
                </div>
                <div class="pt-0.5 text-[15px] font-medium leading-relaxed text-amber-500">
                  {{ $t('common.takeover_started') }}
                </div>
              </div>
            </div>

            <!-- Takeover ended notification -->
            <div v-else-if="msg.type === 'takeover_ended'" class="theme-card flex w-full flex-col gap-3 rounded-2xl rounded-tl-sm p-4">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-green-600 flex-shrink-0 flex items-center justify-center shadow-sm">
                  <span class="text-white text-[11px] font-bold">✓</span>
                </div>
                <div class="theme-text-secondary pt-0.5 text-[15px] font-medium leading-relaxed">
                  {{ msg.message_key ? $t(msg.message_key, msg.params || {}) : msg.message }}
                </div>
              </div>
              <div v-if="msg.image" class="mt-1 overflow-hidden rounded-xl border p-2" style="border-color: var(--border-muted); background: var(--surface-soft); box-shadow: var(--shadow-card);">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Final page state" />
              </div>
            </div>

            <!-- Image message -->
            <div v-else-if="msg.type === 'image'" class="theme-card flex w-full flex-col gap-3 rounded-2xl rounded-tl-sm p-4">
              <div class="flex gap-3">
                <div class="theme-button-strong flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full">
                  <span class="text-[10px] font-bold">AI</span>
                </div>
                <div class="theme-text-secondary font-serif text-[15px] leading-relaxed">{{ msg.description }}</div>
              </div>
              <div class="mt-1 overflow-hidden rounded-xl border p-2" style="border-color: var(--border-muted); background: var(--surface-soft); box-shadow: var(--shadow-card);">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Screenshot" />
              </div>
            </div>

            <!-- File message -->
            <div v-else-if="msg.type === 'file'" class="theme-card flex w-full flex-col gap-3 rounded-2xl rounded-tl-sm p-4">
              <div class="flex gap-3">
                <div class="theme-button-strong flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full">
                  <span class="text-[10px] font-bold">AI</span>
                </div>
                <div class="theme-text-secondary font-serif text-[15px] leading-relaxed">{{ msg.description || $t('common.file_sent') }}</div>
              </div>
              <a
                :href="'data:' + msg.mime_type + ';base64,' + msg.data"
                :download="msg.filename"
                class="theme-button-soft inline-flex max-w-xs items-center gap-3 rounded-xl px-4 py-3 transition-colors"
              >
                <div class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div class="flex flex-col overflow-hidden">
                  <span class="theme-text-primary truncate text-sm font-medium">{{ msg.filename }}</span>
                  <span class="theme-text-muted text-xs">{{ $t('common.click_to_download') }}</span>
                </div>
              </a>
            </div>

            <!-- Action required -->
            <div v-else-if="msg.type === 'action_required'" class="theme-card flex w-full flex-col gap-4 rounded-2xl rounded-tl-sm p-4">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-orange-500 flex-shrink-0 flex items-center justify-center shadow-sm">
                  <span class="text-white text-[12px] font-bold">!</span>
                </div>
                <div class="theme-text-primary pt-0.5 text-[15px] font-medium leading-relaxed">
                  {{ $t('common.action_required') }}：{{ msg.reason }}
                </div>
              </div>
              <div v-if="msg.image" class="mt-2 overflow-hidden rounded-xl border p-2" style="border-color: var(--border-muted); background: var(--surface-soft); box-shadow: var(--shadow-card);">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Action Required" />
              </div>
              <div class="flex flex-wrap gap-3 mt-1">
                <button
                  @click="requestTakeover"
                  class="px-6 py-2.5 bg-amber-500 text-white rounded-xl hover:bg-amber-600 transition-all font-medium text-sm shadow-md active:scale-95"
                >
                  {{ $t('common.takeover_button') }}
                </button>
                <button @click="resumeAgent" class="px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-all font-medium text-sm shadow-md active:scale-95">
                  {{ $t('common.resume_button') }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Sticky bottom input -->
        <div class="theme-gradient-bottom sticky bottom-0 pb-4 pt-4 backdrop-blur-sm">
          <MainInput :minimal="true" @submit="handleUserSubmit" class="!my-0 !h-auto" />
        </div>
      </div>
    </main>

    <!-- Embedded browser view (shown during takeover) -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-all duration-300 ease-out"
        leave-active-class="transition-all duration-200 ease-in"
        enter-from-class="opacity-0 scale-95"
        leave-to-class="opacity-0 scale-95"
      >
        <BrowserView
          v-if="isInTakeover"
          :frame="browserFrame"
          :url="browserUrl"
          :viewport="browserViewport"
          @done="signalTakeoverDone"
          @click="onBrowserClick"
          @double-click="onBrowserDblClick"
          @key="onBrowserKey"
          @type="onBrowserType"
          @scroll="onBrowserScroll"
          @navigate="onBrowserNavigate"
        />
      </Transition>
    </Teleport>
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

</style>
