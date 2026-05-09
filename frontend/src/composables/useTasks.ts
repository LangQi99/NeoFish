import { ref, readonly } from 'vue'

export interface AgentTask {
  id: number
  subject: string
  description: string
  status: 'pending' | 'planning' | 'awaiting_approval' | 'in_progress' | 'completed'
  blockedBy: ReadonlyArray<number>
  blocks: ReadonlyArray<number>
  owner: string
  metadata: Record<string, unknown>
}

export interface TaskSummary {
  total: number
  pending: number
  planning: number
  awaiting_approval: number
  in_progress: number
  completed: number
}

const BASE = 'http://localhost:8000'

const tasks = ref<AgentTask[]>([])
const summary = ref<TaskSummary>({
  total: 0,
  pending: 0,
  planning: 0,
  awaiting_approval: 0,
  in_progress: 0,
  completed: 0,
})
const isLoading = ref(false)

const statusRank: Record<string, number> = {
  planning: 0,
  awaiting_approval: 1,
  in_progress: 2,
  pending: 3,
  completed: 4,
}

function sortTasks(items: AgentTask[]): AgentTask[] {
  return [...items].sort((a, b) => {
    const rankDiff = (statusRank[a.status] ?? 99) - (statusRank[b.status] ?? 99)
    if (rankDiff !== 0) return rankDiff
    return b.id - a.id
  })
}

async function loadTasks() {
  isLoading.value = true
  try {
    const res = await fetch(`${BASE}/tasks`)
    const data = await res.json()
    tasks.value = sortTasks(data.tasks ?? [])
    summary.value = {
      total: data.summary?.total ?? tasks.value.length,
      pending: data.summary?.pending ?? tasks.value.filter(task => task.status === 'pending').length,
      planning: data.summary?.planning ?? tasks.value.filter(task => task.status === 'planning').length,
      awaiting_approval: data.summary?.awaiting_approval ?? tasks.value.filter(task => task.status === 'awaiting_approval').length,
      in_progress: data.summary?.in_progress ?? tasks.value.filter(task => task.status === 'in_progress').length,
      completed: data.summary?.completed ?? tasks.value.filter(task => task.status === 'completed').length,
    }
  } catch (error) {
    console.error('Failed to load tasks', error)
  } finally {
    isLoading.value = false
  }
}

export function useTasks() {
  return {
    tasks: readonly(tasks),
    summary: readonly(summary),
    isLoading: readonly(isLoading),
    loadTasks,
  }
}
