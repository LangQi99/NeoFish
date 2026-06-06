import { ref, readonly } from 'vue'

export interface PlanStep {
  id: number
  content: string
  status: 'pending' | 'in_progress' | 'completed' | 'skipped'
}

export interface PlanSummary {
  total: number
  pending: number
  in_progress: number
  completed: number
  skipped: number
}

const BASE = 'http://localhost:8000'

const steps = ref<PlanStep[]>([])
const planGoal = ref<string>('')
const summary = ref<PlanSummary>({
  total: 0,
  pending: 0,
  in_progress: 0,
  completed: 0,
  skipped: 0,
})
const isLoading = ref(false)

const statusRank: Record<string, number> = {
  in_progress: 0,
  pending: 1,
  completed: 2,
  skipped: 3,
}

function sortSteps(items: PlanStep[]): PlanStep[] {
  return [...items].sort((a, b) => {
    const rankDiff = (statusRank[a.status] ?? 99) - (statusRank[b.status] ?? 99)
    if (rankDiff !== 0) return rankDiff
    return a.id - b.id
  })
}

async function loadTasks() {
  isLoading.value = true
  try {
    const res = await fetch(`${BASE}/tasks`)
    const data = await res.json()
    steps.value = sortSteps(data.steps ?? [])
    planGoal.value = data.plan?.goal ?? ''
    summary.value = {
      total: data.summary?.total ?? steps.value.length,
      pending: data.summary?.pending ?? steps.value.filter(step => step.status === 'pending').length,
      in_progress: data.summary?.in_progress ?? steps.value.filter(step => step.status === 'in_progress').length,
      completed: data.summary?.completed ?? steps.value.filter(step => step.status === 'completed').length,
      skipped: data.summary?.skipped ?? steps.value.filter(step => step.status === 'skipped').length,
    }
  } catch (error) {
    console.error('Failed to load plan', error)
  } finally {
    isLoading.value = false
  }
}

export function useTasks() {
  return {
    steps: readonly(steps),
    planGoal: readonly(planGoal),
    summary: readonly(summary),
    isLoading: readonly(isLoading),
    loadTasks,
  }
}
