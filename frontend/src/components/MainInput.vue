<script setup lang="ts">
import { ref } from 'vue'
import { Plus, ArrowUp, FileText, Globe, X } from 'lucide-vue-next'

const props = defineProps<{
  minimal?: boolean
}>()

const query = ref('')
const pendingImages = ref<string[]>([])  // base64 data-URLs
const fileInputRef = ref<HTMLInputElement | null>(null)
const emit = defineEmits<{
  (e: 'submit', payload: { text: string; images: string[] }): void
}>()

// ── File picker ──────────────────────────────────────────────────────────────
function openFilePicker() {
  fileInputRef.value?.click()
}

function onFilesSelected(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files) return
  Array.from(files).forEach(readImageFile)
  // reset so the same file can be re-selected
  ;(e.target as HTMLInputElement).value = ''
}

function readImageFile(file: File) {
  if (!file.type.startsWith('image/')) return
  const reader = new FileReader()
  reader.onload = () => {
    if (typeof reader.result === 'string') {
      pendingImages.value.push(reader.result)
    }
  }
  reader.readAsDataURL(file)
}

// ── Clipboard paste ──────────────────────────────────────────────────────────
function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) readImageFile(file)
    }
  }
}

function removeImage(idx: number) {
  pendingImages.value.splice(idx, 1)
}

// ── Submit ───────────────────────────────────────────────────────────────────
function handleSubmit(e?: Event) {
  if (e instanceof KeyboardEvent && e.isComposing) return
  const hasText = query.value.trim().length > 0
  const hasImages = pendingImages.value.length > 0
  if (!hasText && !hasImages) return

  emit('submit', {
    text: query.value.trim(),
    images: [...pendingImages.value],
  })
  query.value = ''
  pendingImages.value = []
}
</script>

<template>
  <div class="flex flex-col items-center justify-center w-full max-w-3xl mx-auto px-4" :class="{ 'h-full': !minimal }">
    <!-- Centered prominent text in serif -->
    <h1 v-if="!minimal" class="font-serif text-4xl md:text-5xl lg:text-6xl text-neutral-800 mb-12 tracking-wide font-medium">
      {{ $t('landing.hero_title') }}
    </h1>

    <!-- Image previews -->
    <div v-if="pendingImages.length > 0" class="w-full max-w-2xl mb-2 flex flex-wrap gap-2 px-2">
      <div
        v-for="(src, idx) in pendingImages"
        :key="idx"
        class="relative group w-16 h-16 rounded-xl overflow-hidden border border-neutral-200 shadow-sm flex-shrink-0"
      >
        <img :src="src" class="w-full h-full object-cover" alt="attached image" />
        <button
          @click="removeImage(idx)"
          class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
        >
          <X :size="16" class="text-white" />
        </button>
      </div>
    </div>

    <!-- Floating Input Box -->
    <div
      class="relative w-full max-w-2xl bg-white rounded-3xl shadow-soft p-2 flex items-center transition-all duration-300 focus-within:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.1)] border border-neutral-100"
      :class="pendingImages.length > 0 ? 'rounded-t-xl' : ''"
    >
      <!-- Hidden file input -->
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*"
        multiple
        class="hidden"
        @change="onFilesSelected"
      />

      <!-- Attach button -->
      <button
        @click="openFilePicker"
        :title="$t('input.attach_image')"
        class="p-3 text-neutral-400 hover:text-neutral-700 transition-colors rounded-full hover:bg-neutral-50 ml-1 relative"
        :class="pendingImages.length > 0 ? 'text-blue-500' : ''"
      >
        <Plus :size="22" stroke-width="2" />
        <span
          v-if="pendingImages.length > 0"
          class="absolute -top-0.5 -right-0.5 w-4 h-4 bg-blue-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center"
        >{{ pendingImages.length }}</span>
      </button>

      <input
        v-model="query"
        @keydown.enter="handleSubmit"
        @paste="onPaste"
        type="text"
        class="flex-1 bg-transparent border-none outline-none px-4 py-3 text-lg text-neutral-800 placeholder:text-neutral-400 font-sans"
        :placeholder="$t('landing.input_placeholder')"
      />

      <button
        @click="handleSubmit"
        class="p-3 rounded-2xl transition-colors min-w-[48px] flex items-center justify-center mr-1"
        :class="(query.trim() || pendingImages.length > 0) ? 'bg-black text-white hover:bg-neutral-800' : 'bg-neutral-100 text-neutral-400'"
      >
        <ArrowUp :size="20" stroke-width="3" />
      </button>
    </div>

    <!-- Suggestion Cards -->
    <div v-if="!minimal" class="flex gap-4 mt-8 w-full max-w-2xl px-2">
      <button class="flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm">
        <FileText :size="16" class="text-orange-400" />
        {{ $t('landing.suggest_ppt') }}
      </button>
      <button class="flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/60 hover:bg-white border border-neutral-200/50 text-neutral-600 text-sm font-medium transition-all shadow-sm">
        <Globe :size="16" class="text-blue-400" />
        {{ $t('landing.suggest_analyze') }}
      </button>
    </div>
  </div>
</template>
