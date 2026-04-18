<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ArrowLeft, FileImage, FileText, FileType2, FolderClosed, LoaderCircle, Trash2, Upload } from 'lucide-vue-next'
import { useKnowledge } from '../composables/useKnowledge'

const {
  folders,
  selectedFolderIds,
  activeFolderId,
  folderFiles,
  loading,
  loadingFiles,
  uploading,
  syncing,
  loadFolders,
  loadSelectedFolders,
  loadFolderFiles,
  clearActiveFolder,
  toggleFolder,
  uploadFiles,
  deleteFile,
} = useKnowledge()

const activeFolder = computed(() =>
  folders.value.find(folder => folder.id === activeFolderId.value) || null
)

const selectedSet = computed(() => new Set(selectedFolderIds.value))
const activeFileInputId = 'knowledge-workspace-upload'

function iconForFile(mimeType: string) {
  if (mimeType.startsWith('image/')) return FileImage
  if (
    mimeType === 'application/pdf' ||
    mimeType.includes('word') ||
    mimeType.includes('text') ||
    mimeType.includes('markdown')
  ) {
    return FileText
  }
  return FileType2
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

async function openFolder(folderId: string) {
  await loadFolderFiles(folderId)
}

async function handleToggleActiveFolder(checked: boolean) {
  if (!activeFolderId.value) return
  await toggleFolder(activeFolderId.value, checked)
}

async function handleUploadInActiveFolder(event: Event) {
  if (!activeFolderId.value) return
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  if (!files.length) return
  const ok = await uploadFiles(activeFolderId.value, files)
  if (ok) {
    await loadFolderFiles(activeFolderId.value)
  }
  input.value = ''
}

async function handleDelete(fileId: string) {
  await deleteFile(fileId)
}

onMounted(async () => {
  if (folders.value.length === 0) {
    await loadFolders()
    await loadSelectedFolders()
  }
})
</script>

<template>
  <section class="mx-auto flex h-full w-full max-w-6xl flex-col px-6 pb-6 pt-20">
    <div class="theme-card mb-4 rounded-2xl px-5 py-4">
      <div v-if="!activeFolder" class="flex items-center justify-between">
        <div>
          <h2 class="theme-text-primary text-xl font-semibold">{{ $t('knowledge.workspace_title') }}</h2>
          <p class="theme-text-secondary mt-1 text-sm">{{ $t('knowledge.workspace_hint') }}</p>
        </div>
      </div>

      <div v-else class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <button class="theme-button-soft inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold" @click="clearActiveFolder">
            <ArrowLeft :size="14" />
            {{ $t('knowledge.back_to_folders') }}
          </button>
          <div>
            <h2 class="theme-text-primary text-lg font-semibold">{{ activeFolder.name }}</h2>
            <p class="theme-text-secondary text-xs">{{ activeFolder.path }}</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <label :for="activeFileInputId" class="theme-button-soft inline-flex cursor-pointer items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold">
            <Upload :size="14" />
            {{ uploading ? $t('knowledge.uploading') : $t('knowledge.upload_now') }}
          </label>
          <input
            :id="activeFileInputId"
            class="hidden"
            type="file"
            multiple
            @change="handleUploadInActiveFolder"
          />
          <label class="theme-button-soft inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold">
            <input
              class="h-4 w-4 rounded accent-slate-900"
              type="checkbox"
              :checked="selectedSet.has(activeFolder.id)"
              :disabled="syncing"
              @change="handleToggleActiveFolder(($event.target as HTMLInputElement).checked)"
            />
            <span>{{ $t('knowledge.selected') }}</span>
          </label>
        </div>
      </div>
    </div>

    <div v-if="loading && folders.length === 0" class="theme-text-muted flex flex-1 items-center justify-center gap-2">
      <LoaderCircle :size="18" class="animate-spin" />
      <span class="text-sm">{{ $t('knowledge.loading') }}</span>
    </div>

    <div v-else-if="!activeFolder" class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <button
        v-for="folder in folders"
        :key="folder.id"
        class="theme-card group rounded-2xl p-4 text-left transition-all hover:-translate-y-1"
        @click="openFolder(folder.id)"
      >
        <div class="mb-3 inline-flex rounded-xl bg-sky-500/10 p-2 text-sky-500">
          <FolderClosed :size="18" />
        </div>
        <h3 class="theme-text-primary truncate text-sm font-semibold">{{ folder.name }}</h3>
        <p class="theme-text-muted mt-1 line-clamp-2 text-[11px]">{{ folder.path }}</p>
        <p class="theme-text-secondary mt-2 text-[10px]">{{ folder.file_count }} {{ $t('knowledge.files') }}</p>
      </button>
    </div>

    <div v-else class="theme-scrollbar flex-1 overflow-y-auto">
      <div v-if="loadingFiles" class="theme-text-muted flex h-52 items-center justify-center gap-2">
        <LoaderCircle :size="18" class="animate-spin" />
        <span class="text-sm">{{ $t('knowledge.loading_files') }}</span>
      </div>

      <div v-else-if="folderFiles.length === 0" class="theme-text-muted flex h-52 items-center justify-center text-sm">
        {{ $t('knowledge.empty_files') }}
      </div>

      <div v-else class="grid grid-cols-2 gap-4 pb-4 sm:grid-cols-3 lg:grid-cols-4">
        <article
          v-for="file in folderFiles"
          :key="file.id"
          class="theme-card group rounded-2xl p-3 transition-all hover:-translate-y-1"
        >
          <div class="mb-3 flex aspect-[4/3] items-center justify-center rounded-xl bg-[var(--surface-soft)]">
            <img
              v-if="file.mime_type.startsWith('image/') && file.preview_url"
              :src="file.preview_url"
              class="h-full w-full rounded-xl object-cover"
              :alt="file.name"
            />
            <component :is="iconForFile(file.mime_type)" v-else :size="26" class="theme-text-muted" />
          </div>
          <h4 class="theme-text-primary truncate text-xs font-semibold">{{ file.name }}</h4>
          <p class="theme-text-muted mt-1 text-[10px]">{{ file.size_label }}</p>
          <div class="mt-2 flex items-center justify-between gap-2">
            <span class="theme-text-secondary text-[10px]">{{ formatTime(file.updated_at) }}</span>
            <button
              class="theme-button-soft inline-flex h-7 w-7 items-center justify-center rounded-lg text-red-500"
              @click="handleDelete(file.id)"
            >
              <Trash2 :size="12" />
            </button>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
