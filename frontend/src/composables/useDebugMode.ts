import { ref, watch } from 'vue'

const DEBUG_KEY = 'neofish_debug_mode'

const debugMode = ref(localStorage.getItem(DEBUG_KEY) === 'true')

watch(debugMode, (val) => {
  localStorage.setItem(DEBUG_KEY, String(val))
})

export function useDebugMode() {
  return {
    debugMode,
    toggleDebug: () => {
      debugMode.value = !debugMode.value
    }
  }
}