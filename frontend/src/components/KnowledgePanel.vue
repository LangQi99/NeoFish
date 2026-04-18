<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BookMarked, FolderClosed, LoaderCircle, Plus, RefreshCcw } from 'lucide-vue-next'
import { useKnowledge } from '../composables/useKnowledge'

const {
  folders,
  selectedFolderIds,
  loading,
  syncing,
  creating,
  error,
  loadFolders,
  loadSelectedFolders,
  toggleFolder,
  createFolder,
} = useKnowledge()
const emit = defineEmits<{
  (e: 'open-folder', folderId: string): void
}>()

const selectedSet = computed(() => new Set(selectedFolderIds.value))
const selectedCount = computed(() => selectedFolderIds.value.length)
const folderName = ref('')

function isChecked(folderId: string): boolean {
  return selectedSet.value.has(folderId)
}

function openFolder(folderId: string) {
  emit('open-folder', folderId)
}

async function submitCreateFolder() {
  const ok = await createFolder(folderName.value)
  if (ok) {
    folderName.value = ''
  }
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleString([], {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function init() {
  await loadFolders()
  await loadSelectedFolders()
}

onMounted(() => {
  void init()
})
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="border-b px-3 py-4" style="border-color: var(--border-muted);">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="theme-text-muted text-xs font-semibold uppercase tracking-widest">
          {{ $t('knowledge.title') }}
        </h2>
        <button
          class="theme-button-soft inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-semibold transition-all"
          :disabled="loading || syncing"
          @click="init"
        >
          <RefreshCcw :size="12" :class="loading ? 'animate-spin' : ''" />
          {{ $t('knowledge.refresh') }}
        </button>
      </div>

      <div class="theme-card-soft flex items-center justify-between rounded-xl px-3 py-2">
        <span class="theme-text-secondary text-xs">{{ $t('knowledge.selected') }}</span>
        <span class="theme-text-primary text-sm font-semibold">{{ selectedCount }}</span>
      </div>

      <div class="mt-3">
        <div class="theme-card-soft rounded-xl p-2">
          <p class="theme-text-secondary mb-1 text-[11px] font-semibold">{{ $t('knowledge.create_folder') }}</p>
          <div class="flex items-center gap-2">
            <input
              v-model="folderName"
              class="theme-text-primary w-full rounded-lg border bg-transparent px-2 py-1.5 text-xs outline-none"
              style="border-color: var(--border-muted);"
              :placeholder="$t('knowledge.folder_name_placeholder')"
              @keydown.enter.prevent="submitCreateFolder"
            />
            <button
              class="theme-button-strong inline-flex h-8 w-8 items-center justify-center rounded-lg"
              :disabled="creating"
              @click="submitCreateFolder"
            >
              <Plus :size="14" :class="creating ? 'animate-pulse' : ''" />
            </button>
          </div>
        </div>
      </div>

      <div
        v-if="error"
        class="mt-2 rounded-lg border border-red-300/50 bg-red-100/40 px-2.5 py-1.5 text-[11px] text-red-700"
      >
        {{ $t(error) }}
      </div>
    </div>

    <div class="theme-scrollbar flex-1 overflow-y-auto px-2 py-2">
      <div
        v-if="loading && folders.length === 0"
        class="theme-text-muted flex h-40 flex-col items-center justify-center gap-2"
      >
        <LoaderCircle :size="20" class="animate-spin" />
        <p class="text-xs">{{ $t('knowledge.loading') }}</p>
      </div>

      <div
        v-else-if="folders.length === 0"
        class="theme-text-muted flex h-40 flex-col items-center justify-center gap-2"
      >
        <BookMarked :size="24" />
        <p class="text-xs">{{ $t('knowledge.empty') }}</p>
      </div>

      <div
        v-for="folder in folders"
        :key="folder.id"
        class="group theme-card mb-2 flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 transition-all hover:translate-y-[-1px]"
        @click="openFolder(folder.id)"
      >
        <input
          class="mt-1 h-4 w-4 rounded border-slate-300 accent-slate-900"
          type="checkbox"
          :checked="isChecked(folder.id)"
          :disabled="syncing"
          @click.stop
          @change="toggleFolder(folder.id, ($event.target as HTMLInputElement).checked)"
        />
        <div class="min-w-0 flex-1">
          <div class="theme-text-primary flex items-center gap-2 text-sm font-medium">
            <FolderClosed :size="14" class="theme-text-muted" />
            <span class="truncate">{{ folder.name }}</span>
          </div>
          <p class="theme-text-muted mt-0.5 truncate text-[11px]">{{ folder.path }}</p>
          <div class="theme-text-secondary mt-1 flex items-center gap-2 text-[10px]">
            <span>{{ folder.file_count }} {{ $t('knowledge.files') }}</span>
            <span>·</span>
            <span>{{ folder.size_label }}</span>
            <span>·</span>
            <span>{{ formatTime(folder.updated_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
