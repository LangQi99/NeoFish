<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import MainInput from './components/MainInput.vue'

// WebSocket setup
const ws = ref<WebSocket | null>(null)
const messages = ref<any[]>([])
const isConnected = ref(false)
const hasStarted = ref(false)

function connectWs() {
  ws.value = new WebSocket('ws://localhost:8000/ws/agent')
  
  ws.value.onopen = () => {
    isConnected.value = true
    console.log('WebSocket connected')
  }
  
  ws.value.onmessage = (event) => {
    const data = JSON.parse(event.data)
    messages.value.push(data)
    console.log('Message from server:', data)
  }
  
  ws.value.onclose = () => {
    isConnected.value = false
    console.log('WebSocket disconnected')
    // Attempt to reconnect in 3s
    setTimeout(connectWs, 3000)
  }
}

onMounted(() => {
  connectWs()
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
  }
})

function handleUserSubmit(query: string) {
  hasStarted.value = true
  messages.value.push({ type: 'user', message: query })
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'user_input', message: query }))
  }
}

function resumeAgent() {
  if (ws.value && isConnected.value) {
    ws.value.send(JSON.stringify({ type: 'resume' }))
    messages.value.push({ type: 'info', message: '已发送继续执行指令。' })
  }
}
</script>

<template>
  <div class="h-screen w-full flex bg-[#FDFBF7] font-sans selection:bg-neutral-200">
    <Sidebar />
    
    <main class="flex-1 ml-16 flex flex-col relative h-full">
      <!-- Top nav indicator -->
      <header class="absolute top-0 left-0 w-full p-6 flex justify-end z-10 pointer-events-none">
        <div class="flex items-center gap-2 bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-200/50 shadow-sm">
          <div class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-green-500' : 'bg-red-500'"></div>
          <span class="text-xs font-medium text-neutral-600">{{ isConnected ? 'Agent Ready' : 'Connecting...' }}</span>
        </div>
      </header>
      
      <div v-if="!hasStarted" class="flex-1 overflow-hidden transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] opacity-100 translate-y-0">
        <MainInput @submit="handleUserSubmit" />
      </div>

      <div v-else class="flex-1 flex flex-col max-w-4xl mx-auto w-full pt-20 pb-6 px-4">
        <!-- Chat history stream -->
        <div class="flex-1 overflow-y-auto space-y-6 pb-20 custom-scrollbar pr-4">
          <div v-for="(msg, idx) in messages" :key="idx" 
               class="p-4 rounded-2xl max-w-[85%] animate-fade-in-up"
               :class="msg.type === 'user' ? 'bg-neutral-100 text-neutral-800 ml-auto rounded-tr-sm' : 'bg-white border border-neutral-100 shadow-sm mr-auto rounded-tl-sm'">
            
            <div v-if="msg.type === 'user'" class="text-[15px] leading-relaxed">{{ msg.message }}</div>
            
            <div v-else-if="msg.type === 'info'" class="flex gap-3">
              <div class="w-6 h-6 rounded-full bg-neutral-900 flex-shrink-0 flex items-center justify-center">
                <span class="text-white text-[10px] font-bold">AI</span>
              </div>
              <div class="text-[15px] leading-relaxed text-neutral-700 font-serif">
                {{ msg.message }}
              </div>
            </div>

            <div v-else-if="msg.type === 'action_required'" class="flex flex-col gap-4 w-full">
              <div class="flex gap-3">
                <div class="w-6 h-6 rounded-full bg-orange-500 flex-shrink-0 flex items-center justify-center shadow-sm">
                  <span class="text-white text-[12px] font-bold">!</span>
                </div>
                <div class="text-[15px] leading-relaxed text-neutral-800 font-medium pt-0.5">
                  需要您的协助：{{ msg.reason }}
                </div>
              </div>
              <div v-if="msg.image" class="mt-2 rounded-xl overflow-hidden border border-neutral-200/60 shadow-sm bg-neutral-50/50 p-2">
                <img :src="'data:image/jpeg;base64,' + msg.image" class="w-full h-auto object-contain max-h-[400px] rounded-lg" alt="Action Required" />
              </div>
              <button @click="resumeAgent" class="mt-3 px-6 py-2.5 bg-neutral-900 text-white rounded-xl hover:bg-neutral-800 transition-all self-start font-medium text-sm shadow-md active:scale-95">
                我已处理完毕，继续执行
              </button>
            </div>
          </div>
        </div>

        <!-- Sticky bottom input -->
        <div class="sticky bottom-0 pt-4 bg-gradient-to-t from-[#FDFBF7] pb-4 backdrop-blur-sm">
          <MainInput @submit="handleUserSubmit" class="!my-0 !h-auto" />
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
