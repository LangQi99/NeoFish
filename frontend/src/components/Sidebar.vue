<script setup lang="ts">
import { ref } from 'vue'
import { PlaySquare, Settings, Compass, LayoutGrid, Languages, Bug, Moon, SunMedium, BookMarked } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ChatHistoryPanel from './ChatHistoryPanel.vue'
import GalleryPanel from './GalleryPanel.vue'
import KnowledgePanel from './KnowledgePanel.vue'
import { useDebugMode } from '../composables/useDebugMode'
import { useThemeMode } from '../composables/useThemeMode'

const { locale } = useI18n()
const { debugMode, toggleDebug } = useDebugMode()
const { isDarkMode, toggleTheme } = useThemeMode()
const emit = defineEmits<{
  (e: 'new-chat'): void
  (e: 'select-chat', id: string): void
  (e: 'open-knowledge-workspace', folderId: string): void
}>()

const activePanel = ref<'history' | 'gallery' | 'knowledge' | null>(null)
const panelWidth = 'var(--history-panel-width)'

function toggleHistory() {
  activePanel.value = activePanel.value === 'history' ? null : 'history'
}

function toggleGallery() {
  activePanel.value = activePanel.value === 'gallery' ? null : 'gallery'
}

function toggleKnowledge() {
  activePanel.value = activePanel.value === 'knowledge' ? null : 'knowledge'
}

function toggleLanguage() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
}

function handleNewChat() {
  emit('new-chat')
}

function handleSelectChat(id: string) {
  emit('select-chat', id)
}

function handleOpenFolder(folderId: string) {
  emit('open-knowledge-workspace', folderId)
}
</script>

<template>
  <aside class="relative z-20 flex h-screen flex-shrink-0">
    <div class="theme-rail flex h-full border-r backdrop-blur-xl">
      <div class="flex h-full w-16 flex-col items-center py-6">
        <div class="flex flex-col gap-6">
          <button :title="$t('sidebar.explore')" class="rounded-xl p-2 transition-colors theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]">
            <Compass :size="20" stroke-width="2" />
          </button>
          <button
            :title="$t('sidebar.chat')"
            @click="toggleHistory"
            class="rounded-xl p-2 transition-all duration-300"
            :class="activePanel === 'history' ? 'theme-button-strong shadow-md' : 'theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]'"
          >
            <LayoutGrid :size="20" stroke-width="2" />
          </button>
          <button
            :title="$t('sidebar.gallery')"
            @click="toggleGallery"
            class="rounded-xl p-2 transition-all duration-300"
            :class="activePanel === 'gallery' ? 'theme-button-strong shadow-md' : 'theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]'"
          >
            <PlaySquare :size="20" stroke-width="2" />
          </button>
          <button
            :title="$t('sidebar.knowledge')"
            @click="toggleKnowledge"
            class="rounded-xl p-2 transition-all duration-300"
            :class="activePanel === 'knowledge' ? 'theme-button-strong shadow-md' : 'theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]'"
          >
            <BookMarked :size="20" stroke-width="2" />
          </button>
        </div>

        <div class="mt-auto flex flex-col gap-4">
          <button
            @click="toggleLanguage"
            class="flex flex-col items-center gap-0.5 rounded-xl p-2 transition-all theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]"
            title="Switch Language / 切换语言"
          >
            <Languages :size="20" stroke-width="2" />
            <span class="text-[9px] font-bold uppercase">{{ locale === 'zh' ? 'EN' : 'ZH' }}</span>
          </button>

          <button
            @click="toggleTheme"
            class="rounded-xl p-2 transition-all"
            :class="isDarkMode ? 'bg-sky-500/15 text-sky-300' : 'bg-neutral-900/5 text-neutral-500 hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]'"
            :title="isDarkMode ? $t('sidebar.theme_light') : $t('sidebar.theme_dark')"
          >
            <SunMedium v-if="isDarkMode" :size="20" stroke-width="2" />
            <Moon v-else :size="20" stroke-width="2" />
          </button>

          <button
            @click="toggleDebug"
            class="rounded-xl p-2 transition-all"
            :class="debugMode ? 'bg-amber-500/15 text-amber-400' : 'theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]'"
            :title="debugMode ? $t('sidebar.debug_on') : $t('sidebar.debug_off')"
          >
            <Bug :size="20" stroke-width="2" />
          </button>

          <button :title="$t('sidebar.settings')" class="rounded-xl p-2 transition-colors theme-text-muted hover:bg-[var(--surface-soft)] hover:text-[color:var(--text-primary)]">
            <Settings :size="20" stroke-width="2" />
          </button>
        </div>
      </div>

      <div
        class="history-panel-shell h-full overflow-hidden transition-[width,opacity] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
        :class="activePanel ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'"
        :style="{ width: activePanel ? panelWidth : '0px' }"
      >
        <div
          class="theme-panel flex h-full flex-col border-l backdrop-blur-xl"
          :style="{ width: panelWidth }"
        >
          <ChatHistoryPanel
            v-if="activePanel === 'history'"
            @new-chat="handleNewChat"
            @select="handleSelectChat"
          />
          <GalleryPanel v-else-if="activePanel === 'gallery'" />
          <KnowledgePanel v-else-if="activePanel === 'knowledge'" @open-folder="handleOpenFolder" />
        </div>
      </div>
    </div>
  </aside>
</template>
