import { ref } from 'vue'

const BASE = 'http://localhost:8000'

export type BrowserMode = 'headless' | 'local_chrome'

const mode = ref<BrowserMode>('headless')
const switching = ref(false)
const lastError = ref<string | null>(null)
let initialized = false

async function refresh() {
  try {
    const res = await fetch(`${BASE}/browser/mode`)
    if (!res.ok) return
    const data = await res.json()
    if (data && (data.mode === 'headless' || data.mode === 'local_chrome')) {
      mode.value = data.mode
    }
  } catch {
    // silent — backend may not be up yet
  }
}

async function setMode(next: BrowserMode) {
  if (switching.value || mode.value === next) return
  switching.value = true
  lastError.value = null
  try {
    const res = await fetch(`${BASE}/browser/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: next }),
    })
    if (!res.ok) {
      const text = await res.text()
      lastError.value = text || `HTTP ${res.status}`
      return
    }
    const data = await res.json()
    if (data && (data.mode === 'headless' || data.mode === 'local_chrome')) {
      mode.value = data.mode
    }
  } catch (e) {
    lastError.value = String(e)
  } finally {
    switching.value = false
  }
}

async function toggle() {
  await setMode(mode.value === 'headless' ? 'local_chrome' : 'headless')
}

export function useBrowserMode() {
  if (!initialized) {
    initialized = true
    refresh()
  }
  return { mode, switching, lastError, refresh, setMode, toggle }
}
