import { computed, ref, watch } from 'vue'

type ThemeMode = 'light' | 'dark'

const THEME_KEY = 'neofish_theme_mode'

function getInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'light'

  const stored = window.localStorage.getItem(THEME_KEY)
  if (stored === 'light' || stored === 'dark') return stored

  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const themeMode = ref<ThemeMode>(getInitialTheme())
let syncInitialized = false

function ensureThemeSync() {
  if (syncInitialized || typeof window === 'undefined') return

  watch(
    themeMode,
    (value) => {
      window.localStorage.setItem(THEME_KEY, value)
      document.documentElement.dataset.theme = value
    },
    { immediate: true }
  )

  syncInitialized = true
}

export function useThemeMode() {
  ensureThemeSync()

  return {
    themeMode,
    isDarkMode: computed(() => themeMode.value === 'dark'),
    toggleTheme: () => {
      themeMode.value = themeMode.value === 'dark' ? 'light' : 'dark'
    },
  }
}
