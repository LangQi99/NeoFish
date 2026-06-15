<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircle2, ChevronLeft, Circle, LoaderCircle, MinusCircle } from 'lucide-vue-next'
import type { PlanStep, PlanSummary } from '../composables/useTasks'

const props = defineProps<{
  steps: ReadonlyArray<PlanStep>
  summary: PlanSummary
  loading: boolean
}>()

const isOpen = ref(false)
const visibleSteps = computed(() => props.steps.slice(0, 10))
const hiddenStepCount = computed(() => Math.max(0, props.steps.length - visibleSteps.value.length))
const completedRatio = computed(() => {
  if (props.summary.total <= 0) return 0
  return Math.round((props.summary.completed / props.summary.total) * 100)
})
</script>

<template>
  <div class="relative h-full w-7 overflow-visible" @mouseleave="isOpen = false">
    <button
      class="theme-panel absolute right-0 top-1/2 z-20 flex h-16 w-7 -translate-y-1/2 items-center justify-center rounded-l-2xl rounded-r-none border-r-0"
      :title="$t('tasks.toggle')"
      @mouseenter="isOpen = true"
    >
      <ChevronLeft :size="16" class="theme-text-secondary" />
    </button>

    <aside
      class="theme-panel absolute right-7 top-0 h-full w-[17rem] overflow-hidden rounded-l-[1.75rem] rounded-r-none border-r-0 px-3 py-4 transition-all duration-200 ease-out"
      :class="isOpen ? 'translate-x-0 opacity-100' : 'pointer-events-none translate-x-full opacity-0'"
      @mouseenter="isOpen = true"
    >
      <div class="theme-scrollbar h-full overflow-y-auto pr-1">
        <div class="space-y-1.5">
          <div class="theme-card-soft mb-3 rounded-2xl px-3 py-3">
            <div class="mb-2 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="theme-text-primary truncate text-sm font-semibold">{{ $t('tasks.title') }}</p>
                <p class="theme-text-muted mt-0.5 text-[11px]">
                  {{ $t('tasks.progress', { completed: summary.completed, total: summary.total }) }}
                </p>
              </div>
              <span class="theme-text-primary flex-shrink-0 text-sm font-semibold">{{ completedRatio }}%</span>
            </div>

            <div class="h-1.5 overflow-hidden rounded-full bg-[var(--surface)]">
              <div
                class="h-full rounded-full bg-emerald-500 transition-[width] duration-300"
                :style="{ width: `${completedRatio}%` }"
              ></div>
            </div>

            <div class="mt-3 grid grid-cols-3 gap-1.5 text-center">
              <div class="rounded-xl bg-[var(--surface)] px-2 py-1.5">
                <p class="theme-text-muted text-[10px]">{{ $t('tasks.in_progress') }}</p>
                <p class="text-sm font-semibold text-sky-400">{{ summary.in_progress }}</p>
              </div>
              <div class="rounded-xl bg-[var(--surface)] px-2 py-1.5">
                <p class="theme-text-muted text-[10px]">{{ $t('tasks.pending') }}</p>
                <p class="theme-text-primary text-sm font-semibold">{{ summary.pending }}</p>
              </div>
              <div class="rounded-xl bg-[var(--surface)] px-2 py-1.5">
                <p class="theme-text-muted text-[10px]">{{ $t('tasks.done') }}</p>
                <p class="text-sm font-semibold text-emerald-500">{{ summary.completed }}</p>
              </div>
            </div>
          </div>

          <div
            v-if="loading && visibleSteps.length === 0"
            class="flex items-center gap-3 rounded-2xl px-3 py-2.5"
          >
            <LoaderCircle :size="16" class="animate-spin text-sky-400" />
            <span class="theme-text-secondary truncate text-sm">{{ $t('tasks.loading_inline') }}</span>
          </div>

          <div
            v-else-if="visibleSteps.length === 0"
            class="flex items-center gap-3 rounded-2xl px-3 py-2.5"
          >
            <Circle :size="14" class="theme-text-muted" />
            <span class="theme-text-secondary truncate text-sm">{{ $t('tasks.empty_inline') }}</span>
          </div>

          <div
            v-for="step in visibleSteps"
            :key="step.id"
            class="theme-card-soft flex items-center gap-3 rounded-2xl px-3 py-2.5"
          >
            <CheckCircle2
              v-if="step.status === 'completed'"
              :size="16"
              class="flex-shrink-0 text-emerald-500"
            />
            <LoaderCircle
              v-else-if="step.status === 'in_progress'"
              :size="16"
              class="flex-shrink-0 animate-spin text-sky-400"
            />
            <MinusCircle
              v-else-if="step.status === 'skipped'"
              :size="16"
              class="flex-shrink-0 theme-text-muted"
            />
            <Circle
              v-else
              :size="14"
              class="flex-shrink-0 theme-text-muted"
            />
            <span class="theme-text-primary truncate text-sm leading-6">{{ step.content }}</span>
          </div>

          <div
            v-if="hiddenStepCount > 0"
            class="theme-text-muted px-3 py-2 text-center text-[11px]"
          >
            {{ $t('tasks.more_steps', { count: hiddenStepCount }) }}
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
