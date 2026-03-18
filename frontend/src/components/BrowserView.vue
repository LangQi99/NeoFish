<script setup lang="ts">
import { ref, watch } from 'vue'
import { RotateCw } from 'lucide-vue-next'

const props = defineProps<{
  frame: string  // base64-encoded JPEG screenshot
  url: string
  viewport: { width: number; height: number }
}>()

const emit = defineEmits<{
  (e: 'done'): void
  (e: 'click', payload: { x: number; y: number; button: string }): void
  (e: 'double-click', payload: { x: number; y: number }): void
  (e: 'key', payload: { key: string }): void
  (e: 'type', payload: { text: string }): void
  (e: 'scroll', payload: { deltaX: number; deltaY: number }): void
  (e: 'navigate', payload: { url: string }): void
}>()

const browserContainer = ref<HTMLElement | null>(null)
const urlInput = ref(props.url)

watch(() => props.url, (newUrl) => {
  urlInput.value = newUrl
})

/** Map a mouse event position to browser viewport coordinates. */
function getCoords(event: MouseEvent): { x: number; y: number } {
  const el = browserContainer.value!
  const rect = el.getBoundingClientRect()

  // The screenshot is displayed with object-contain so it may be letterboxed.
  // Calculate the actual rendered image rect inside the container.
  const containerW = rect.width
  const containerH = rect.height
  const vpW = props.viewport.width
  const vpH = props.viewport.height
  const imgAspect = vpW / vpH
  const containerAspect = containerW / containerH

  let renderedW: number, renderedH: number, offsetX: number, offsetY: number
  if (imgAspect > containerAspect) {
    // Letterboxed on top and bottom
    renderedW = containerW
    renderedH = containerW / imgAspect
    offsetX = 0
    offsetY = (containerH - renderedH) / 2
  } else {
    // Pillarboxed on left and right
    renderedH = containerH
    renderedW = containerH * imgAspect
    offsetX = (containerW - renderedW) / 2
    offsetY = 0
  }

  const relX = event.clientX - rect.left - offsetX
  const relY = event.clientY - rect.top - offsetY
  return {
    x: Math.round(Math.max(0, Math.min(vpW, (relX / renderedW) * vpW))),
    y: Math.round(Math.max(0, Math.min(vpH, (relY / renderedH) * vpH))),
  }
}

function onClick(event: MouseEvent) {
  browserContainer.value?.focus()
  const { x, y } = getCoords(event)
  const button = event.button === 1 ? 'middle' : event.button === 2 ? 'right' : 'left'
  emit('click', { x, y, button })
}

function onDblClick(event: MouseEvent) {
  const { x, y } = getCoords(event)
  emit('double-click', { x, y })
}

function onWheel(event: WheelEvent) {
  event.preventDefault()
  emit('scroll', { deltaX: event.deltaX, deltaY: event.deltaY })
}

function onContextMenu(event: MouseEvent) {
  event.preventDefault()
  const { x, y } = getCoords(event)
  emit('click', { x, y, button: 'right' })
}

function onKeyDown(event: KeyboardEvent) {
  event.preventDefault()
  event.stopPropagation()
  const key = event.key
  // Single printable characters without modifier keys → use type for natural IME support
  if (
    key.length === 1 &&
    !event.ctrlKey &&
    !event.altKey &&
    !event.metaKey
  ) {
    emit('type', { text: key })
  } else {
    // Special / modified keys → press (Playwright key name format)
    let playwrightKey = key
    if (event.ctrlKey && key.length === 1) {
      playwrightKey = `Control+${key.toUpperCase()}`
    } else if (event.metaKey && key.length === 1) {
      playwrightKey = `Meta+${key.toUpperCase()}`
    } else if (event.altKey && key.length === 1) {
      playwrightKey = `Alt+${key}`
    }
    emit('key', { key: playwrightKey })
  }
}

function navigate() {
  let url = urlInput.value.trim()
  if (!url) return
  // Prepend https:// if no protocol is given
  if (!/^[a-z][a-z0-9+\-.]*:\/\//i.test(url)) {
    url = 'https://' + url
    urlInput.value = url
  }
  // Validate the URL before emitting
  try {
    new URL(url)
  } catch {
    return  // silently ignore malformed URLs
  }
  emit('navigate', { url })
}
</script>

<template>
  <!-- Full-screen modal overlay -->
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
    <div
      class="bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
      style="width: min(1300px, calc(100vw - 2rem)); height: min(900px, calc(100vh - 2rem));"
    >
      <!-- Toolbar -->
      <div class="flex items-center gap-2 px-4 py-2.5 border-b border-neutral-200 bg-neutral-50 flex-shrink-0">
        <!-- Traffic-light dots -->
        <div class="flex items-center gap-1.5 mr-1">
          <div class="w-3 h-3 rounded-full bg-red-400"></div>
          <div class="w-3 h-3 rounded-full bg-yellow-400"></div>
          <div class="w-3 h-3 rounded-full bg-green-400"></div>
        </div>

        <!-- URL bar -->
        <input
          v-model="urlInput"
          @keydown.enter.stop="navigate"
          @keydown.stop
          type="text"
          class="flex-1 px-3 py-1.5 rounded-lg border border-neutral-200 bg-white text-sm font-mono outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200 transition-all"
          :placeholder="$t('browser.url_placeholder')"
          spellcheck="false"
        />

        <!-- Reload / navigate button -->
        <button
          @click="navigate"
          class="p-1.5 rounded-lg hover:bg-neutral-200 text-neutral-500 transition-colors"
          :title="$t('browser.navigate')"
        >
          <RotateCw :size="15" />
        </button>

        <!-- Done button -->
        <button
          @click="$emit('done')"
          class="px-4 py-1.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-700 transition-colors"
        >
          {{ $t('common.takeover_done_button') }}
        </button>
      </div>

      <!-- Browser viewport area -->
      <div
        ref="browserContainer"
        class="flex-1 relative bg-neutral-200 overflow-hidden cursor-crosshair focus:outline-none select-none"
        tabindex="0"
        @click.prevent="onClick"
        @dblclick.prevent="onDblClick"
        @wheel.prevent="onWheel"
        @contextmenu.prevent="onContextMenu"
        @keydown="onKeyDown"
      >
        <!-- Screenshot frame -->
        <img
          v-if="frame"
          :src="'data:image/jpeg;base64,' + frame"
          class="absolute inset-0 w-full h-full object-contain pointer-events-none select-none"
          draggable="false"
          alt="browser view"
        />
        <!-- Loading state -->
        <div v-else class="flex items-center justify-center h-full text-neutral-400 gap-2">
          <svg class="animate-spin w-5 h-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
          </svg>
          <span class="text-sm">{{ $t('browser.loading') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
