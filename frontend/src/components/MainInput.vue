<script setup lang="ts">
import { ref } from 'vue'
import { Plus, ArrowUp, FileText, Globe } from 'lucide-vue-next'

const query = ref('')
const emit = defineEmits(['submit'])

function handleSubmit() {
  if (!query.value.trim()) return
  emit('submit', query.value)
  query.value = ''
}
</script>

<template>
  <div class="flex flex-col items-center justify-center w-full max-w-3xl mx-auto px-4 h-full">
    <!-- Centered prominent text in serif -->
    <h1 class="font-serif text-4xl md:text-5xl lg:text-6xl text-neutral-800 mb-12 tracking-wide font-medium">
      我能为你做什么？
    </h1>

    <!-- Floating Input Box -->
    <div class="relative w-full max-w-2xl bg-white rounded-3xl shadow-soft p-2 flex items-center transition-all duration-300 focus-within:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.1)] border border-neutral-100">
      <button class="p-3 text-neutral-400 hover:text-neutral-700 transition-colors rounded-full hover:bg-neutral-50 ml-1">
        <Plus :size="22" stroke-width="2" />
      </button>
      
      <input 
        v-model="query"
        @keydown.enter="handleSubmit"
        type="text" 
        class="flex-1 bg-transparent border-none outline-none px-4 py-3 text-lg text-neutral-800 placeholder:text-neutral-400 font-sans"
        placeholder="发送任何工作任务，或者问我任何问题"
      />
      
      <button 
        @click="handleSubmit"
        class="p-3 rounded-2xl transition-colors min-w-[48px] flex items-center justify-center mr-1"
        :class="query.trim() ? 'bg-black text-white hover:bg-neutral-800' : 'bg-neutral-100 text-neutral-400'"
      >
        <ArrowUp :size="20" stroke-width="3" />
      </button>
    </div>

    <!-- Suggestion Cards -->
    <div class="flex gap-4 mt-8 w-full max-w-2xl px-2">
      <button class="flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm">
        <FileText :size="16" class="text-orange-400" />
        制作演示文稿
      </button>
      <button class="flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm">
        <Globe :size="16" class="text-blue-400" />
        分析网页内容
      </button>
    </div>
  </div>
</template>
