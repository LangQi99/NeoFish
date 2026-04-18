import { readonly, ref } from 'vue'

export interface KnowledgeFolder {
    id: string
    name: string
    path: string
    file_count: number
    updated_at: string
    size_label: string
}

export interface KnowledgeFileItem {
    id: string
    name: string
    mime_type: string
    size_label: string
    updated_at: string
    preview_url?: string
}

const BASE = 'http://localhost:8000'

const folders = ref<KnowledgeFolder[]>([])
const selectedFolderIds = ref<string[]>([])
const activeFolderId = ref<string>('')
const folderFiles = ref<KnowledgeFileItem[]>([])
const loading = ref(false)
const loadingFiles = ref(false)
const syncing = ref(false)
const creating = ref(false)
const uploading = ref(false)
const error = ref('')
const usingDemoData = ref(false)

const demoFolders: KnowledgeFolder[] = [
    {
        id: 'product_docs',
        name: '产品文档库',
        path: 'knowledge/product_docs',
        file_count: 26,
        updated_at: '2026-04-18T09:20:00',
        size_label: '12.4 MB',
    },
    {
        id: 'tech_arch',
        name: '技术架构库',
        path: 'knowledge/tech_arch',
        file_count: 18,
        updated_at: '2026-04-17T16:45:00',
        size_label: '7.9 MB',
    },
    {
        id: 'ops_playbook',
        name: '运维手册库',
        path: 'knowledge/ops_playbook',
        file_count: 31,
        updated_at: '2026-04-16T21:05:00',
        size_label: '20.1 MB',
    },
]

const demoFilesByFolder: Record<string, KnowledgeFileItem[]> = {
    product_docs: [
        { id: 'prd_1', name: '产品需求说明书-v2.pdf', mime_type: 'application/pdf', size_label: '1.8 MB', updated_at: '2026-04-17T10:30:00' },
        { id: 'prd_2', name: '用户调研访谈纪要.md', mime_type: 'text/markdown', size_label: '246 KB', updated_at: '2026-04-15T08:25:00' },
        { id: 'prd_3', name: '流程图-下单链路.png', mime_type: 'image/png', size_label: '732 KB', updated_at: '2026-04-14T19:10:00' },
    ],
    tech_arch: [
        { id: 'arch_1', name: '系统架构总览.drawio', mime_type: 'application/octet-stream', size_label: '412 KB', updated_at: '2026-04-17T16:45:00' },
        { id: 'arch_2', name: '服务治理设计文档.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size_label: '589 KB', updated_at: '2026-04-16T11:00:00' },
    ],
    ops_playbook: [
        { id: 'ops_1', name: '故障演练手册.pdf', mime_type: 'application/pdf', size_label: '2.1 MB', updated_at: '2026-04-13T09:12:00' },
        { id: 'ops_2', name: '监控面板截图.jpg', mime_type: 'image/jpeg', size_label: '964 KB', updated_at: '2026-04-12T21:38:00' },
    ],
}

function normalizeFolder(raw: any): KnowledgeFolder {
    return {
        id: String(raw.id ?? raw.name ?? raw.path ?? crypto.randomUUID()),
        name: String(raw.name ?? raw.id ?? 'Unnamed Folder'),
        path: String(raw.path ?? ''),
        file_count: Number(raw.file_count ?? raw.fileCount ?? 0),
        updated_at: String(raw.updated_at ?? raw.updatedAt ?? ''),
        size_label: String(raw.size_label ?? raw.size ?? '-'),
    }
}

function normalizeFile(raw: any): KnowledgeFileItem {
    const previewPath = raw.preview_url ? String(raw.preview_url) : ''
    return {
        id: String(raw.id ?? raw.name ?? crypto.randomUUID()),
        name: String(raw.name ?? 'Unnamed File'),
        mime_type: String(raw.mime_type ?? raw.mimeType ?? 'application/octet-stream'),
        size_label: String(raw.size_label ?? raw.size ?? '-'),
        updated_at: String(raw.updated_at ?? raw.updatedAt ?? ''),
        preview_url: previewPath
            ? (previewPath.startsWith('http') ? previewPath : `${BASE}${previewPath}`)
            : undefined,
    }
}

async function loadFolders() {
    loading.value = true
    error.value = ''
    try {
        const res = await fetch(`${BASE}/knowledge/folders`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data?.folders) ? data.folders : []
        folders.value = list.map(normalizeFolder)
        usingDemoData.value = false
    } catch (err) {
        console.warn('Failed to load knowledge folders, fallback to demo data', err)
        folders.value = demoFolders
        usingDemoData.value = true
        error.value = 'knowledge.fallback_demo'
    } finally {
        loading.value = false
    }
}

async function loadSelectedFolders() {
    try {
        const res = await fetch(`${BASE}/knowledge/selected`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const selected = Array.isArray(data?.selected_folder_ids)
            ? data.selected_folder_ids
            : Array.isArray(data?.selected)
                ? data.selected
                : []
        selectedFolderIds.value = selected.map((id: unknown) => String(id))
    } catch (err) {
        console.warn('Failed to load selected knowledge folders', err)
        if (usingDemoData.value && selectedFolderIds.value.length === 0) {
            selectedFolderIds.value = ['product_docs']
        }
    }
}

async function toggleFolder(folderId: string, checked: boolean) {
    syncing.value = true
    error.value = ''

    if (usingDemoData.value) {
        if (checked && !selectedFolderIds.value.includes(folderId)) {
            selectedFolderIds.value = [...selectedFolderIds.value, folderId]
        }
        if (!checked) {
            selectedFolderIds.value = selectedFolderIds.value.filter(id => id !== folderId)
        }
        syncing.value = false
        return
    }

    try {
        const endpoint = checked ? '/knowledge/select' : '/knowledge/deselect'
        const res = await fetch(`${BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_id: folderId }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        await loadSelectedFolders()
    } catch (err) {
        console.error('Failed to update folder selection', err)
        error.value = checked ? 'knowledge.select_failed' : 'knowledge.deselect_failed'
    } finally {
        syncing.value = false
    }
}

async function createFolder(name: string): Promise<boolean> {
    const folderName = name.trim()
    if (!folderName) {
        error.value = 'knowledge.folder_name_required'
        return false
    }

    creating.value = true
    error.value = ''

    if (usingDemoData.value) {
        const id = folderName.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, '_')
        if (folders.value.some(f => f.id === id || f.name === folderName)) {
            creating.value = false
            error.value = 'knowledge.folder_exists'
            return false
        }
        folders.value = [
            {
                id,
                name: folderName,
                path: `knowledge/${id}`,
                file_count: 0,
                updated_at: new Date().toISOString(),
                size_label: '0 B',
            },
            ...folders.value,
        ]
        creating.value = false
        return true
    }

    try {
        const res = await fetch(`${BASE}/knowledge/folders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: folderName }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        await loadFolders()
        return true
    } catch (err) {
        console.error('Failed to create folder', err)
        error.value = 'knowledge.create_failed'
        return false
    } finally {
        creating.value = false
    }
}

async function uploadFiles(folderId: string, files: File[]): Promise<boolean> {
    if (!folderId) {
        error.value = 'knowledge.folder_required'
        return false
    }
    if (!files.length) {
        error.value = 'knowledge.files_required'
        return false
    }

    uploading.value = true
    error.value = ''

    if (usingDemoData.value) {
        folders.value = folders.value.map(folder => {
            if (folder.id !== folderId) return folder
            const nextCount = folder.file_count + files.length
            return {
                ...folder,
                file_count: nextCount,
                updated_at: new Date().toISOString(),
                size_label: folder.size_label === '0 B' ? '1.2 MB' : folder.size_label,
            }
        })
        const existing = demoFilesByFolder[folderId] ?? []
        const incoming = files.map((file, index) => ({
            id: `${folderId}_${Date.now()}_${index}`,
            name: file.name,
            mime_type: file.type || 'application/octet-stream',
            size_label: `${Math.max(1, Math.round(file.size / 1024))} KB`,
            updated_at: new Date().toISOString(),
        }))
        demoFilesByFolder[folderId] = [...incoming, ...existing]
        if (activeFolderId.value === folderId) {
            folderFiles.value = demoFilesByFolder[folderId] ?? []
        }
        uploading.value = false
        return true
    }

    try {
        const form = new FormData()
        form.append('folder_id', folderId)
        files.forEach(file => form.append('files', file))
        const res = await fetch(`${BASE}/knowledge/upload`, {
            method: 'POST',
            body: form,
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        await loadFolders()
        return true
    } catch (err) {
        console.error('Failed to upload files', err)
        error.value = 'knowledge.upload_failed'
        return false
    } finally {
        uploading.value = false
    }
}

async function loadFolderFiles(folderId: string) {
    activeFolderId.value = folderId
    loadingFiles.value = true
    error.value = ''

    if (usingDemoData.value) {
        folderFiles.value = (demoFilesByFolder[folderId] ?? []).map(item => ({ ...item }))
        loadingFiles.value = false
        return
    }

    try {
        const res = await fetch(`${BASE}/knowledge/folders/${encodeURIComponent(folderId)}/files`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data?.files) ? data.files : []
        folderFiles.value = list.map(normalizeFile)
    } catch (err) {
        console.error('Failed to load folder files', err)
        folderFiles.value = []
        error.value = 'knowledge.load_files_failed'
    } finally {
        loadingFiles.value = false
    }
}

function clearActiveFolder() {
    activeFolderId.value = ''
    folderFiles.value = []
}

async function deleteFile(fileId: string): Promise<boolean> {
    if (!activeFolderId.value) return false

    if (usingDemoData.value) {
        demoFilesByFolder[activeFolderId.value] = (demoFilesByFolder[activeFolderId.value] ?? []).filter(
            file => file.id !== fileId
        )
        folderFiles.value = (demoFilesByFolder[activeFolderId.value] ?? []).map(item => ({ ...item }))
        return true
    }

    try {
        const res = await fetch(`${BASE}/knowledge/files/${encodeURIComponent(fileId)}`, {
            method: 'DELETE',
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        await loadFolderFiles(activeFolderId.value)
        return true
    } catch (err) {
        console.error('Failed to delete file', err)
        error.value = 'knowledge.delete_file_failed'
        return false
    }
}

export function useKnowledge() {
    return {
        folders: readonly(folders),
        selectedFolderIds: readonly(selectedFolderIds),
        activeFolderId: readonly(activeFolderId),
        folderFiles: readonly(folderFiles),
        loading: readonly(loading),
        loadingFiles: readonly(loadingFiles),
        syncing: readonly(syncing),
        creating: readonly(creating),
        uploading: readonly(uploading),
        error: readonly(error),
        usingDemoData: readonly(usingDemoData),
        loadFolders,
        loadSelectedFolders,
        toggleFolder,
        createFolder,
        uploadFiles,
        loadFolderFiles,
        clearActiveFolder,
        deleteFile,
    }
}
