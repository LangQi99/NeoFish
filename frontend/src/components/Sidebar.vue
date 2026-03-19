<script setup lang="ts">
import { ref } from 'vue'
import { PlaySquare, Settings, Compass, LayoutGrid, Languages, Bug } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import ChatHistoryPanel from './ChatHistoryPanel.vue'
import { useDebugMode } from '../composables/useDebugMode'

const { locale, t } = useI18n()
const { debugMode, toggleDebug } = useDebugMode()
const emit = defineEmits<{
  (e: 'new-chat'): void
  (e: 'select-chat', id: string): void
}>()

const historyOpen = ref(false)

function toggleHistory() {
  historyOpen.value = !historyOpen.value
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
</script>

<template>
  <div class="flex h-screen fixed left-0 top-0 z-50">
    <!-- Icon rail -->
    <aside class="w-16 h-full flex flex-col items-center py-6 border-r border-neutral-200/50 bg-white/50 backdrop-blur-sm">
      <!-- Top Icons -->
      <div class="flex flex-col gap-6">
        <button :title="$t('sidebar.explore')" class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
          <Compass :size="20" stroke-width="2" />
        </button>
        <button
          :title="$t('sidebar.chat')"
          @click="toggleHistory"
          class="p-2 rounded-xl transition-colors"
          :class="historyOpen ? 'text-neutral-800 bg-neutral-100' : 'text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100'"
        >
          <LayoutGrid :size="20" stroke-width="2" />
        </button>
        <button :title="$t('sidebar.gallery')" class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
          <PlaySquare :size="20" stroke-width="2" />
        </button>
      </div>

      <div class="mt-auto flex flex-col gap-4">
        <!-- Language Toggle -->
        <button
          @click="toggleLanguage"
          class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-all flex flex-col items-center gap-0.5"
          title="Switch Language / 切换语言"
        >
          <Languages :size="20" stroke-width="2" />
          <span class="text-[9px] font-bold uppercase">{{ locale === 'zh' ? 'EN' : 'ZH' }}</span>
        </button>

        <button
          @click="toggleDebug"
          class="p-2 rounded-xl transition-all"
          :class="debugMode ? 'text-amber-600 bg-amber-50' : 'text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100'"
          :title="debugMode ? $t('sidebar.debug_on') : $t('sidebar.debug_off')"
        >
          <Bug :size="20" stroke-width="2" />
        </button>

        <button :title="$t('sidebar.settings')" class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
          <Settings :size="20" stroke-width="2" />
        </button>
      </div>
    </aside>

    <!-- History Panel (slide-in) -->
    <Transition
      enter-active-class="transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
      leave-active-class="transition-all duration-200 ease-in"
      enter-from-class="opacity-0 -translate-x-4"
      leave-to-class="opacity-0 -translate-x-4"
    >
      <div
        v-if="historyOpen"
        class="w-64 h-full border-r border-neutral-200/50 bg-white/90 backdrop-blur-md shadow-md flex flex-col"
      >
        <ChatHistoryPanel
          @new-chat="handleNewChat"
          @select="handleSelectChat"
        />
      </div>
    </Transition>
  </div>
</template>
