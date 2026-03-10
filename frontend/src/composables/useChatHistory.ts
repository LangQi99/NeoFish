import { ref, readonly } from 'vue'

export interface ChatSession {
  id: string
  title: string
  created_at: string
  preview: string
  message_count: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  images?: string[]
}

const BASE = 'http://localhost:8000'

const sessions = ref<ChatSession[]>([])
const activeChatId = ref<string | null>(null)

async function loadSessions() {
  try {
    const res = await fetch(`${BASE}/chats`)
    sessions.value = await res.json()
  } catch (e) {
    console.error('Failed to load sessions', e)
  }
}

async function createNewChat(): Promise<ChatSession> {
  const res = await fetch(`${BASE}/chats`, { method: 'POST' })
  const session: ChatSession = await res.json()
  sessions.value.unshift(session)
  activeChatId.value = session.id
  return session
}

async function deleteChat(id: string) {
  await fetch(`${BASE}/chats/${id}`, { method: 'DELETE' })
  sessions.value = sessions.value.filter(s => s.id !== id)
  if (activeChatId.value === id) {
    activeChatId.value = sessions.value[0]?.id ?? null
  }
}

async function renameChat(id: string, title: string) {
  const res = await fetch(`${BASE}/chats/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
  const updated: ChatSession = await res.json()
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx !== -1) sessions.value[idx] = updated
}

async function loadMessages(id: string): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`${BASE}/chats/${id}/messages`)
    return await res.json()
  } catch {
    return []
  }
}

function refreshSession(id: string | null, patch: Partial<ChatSession>) {
  if (!id) return
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx !== -1) sessions.value[idx] = { ...sessions.value[idx], ...patch } as ChatSession
}

export function useChatHistory() {
  return {
    sessions: readonly(sessions),
    activeChatId,
    loadSessions,
    createNewChat,
    deleteChat,
    renameChat,
    loadMessages,
    refreshSession,
  }
}
