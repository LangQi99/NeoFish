<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircle2, ChevronLeft, Circle, LoaderCircle, MinusCircle } from 'lucide-vue-next'
import type { PlanStep } from '../composables/useTasks'

const props = defineProps<{
  steps: ReadonlyArray<PlanStep>
  loading: boolean
}>()

const isOpen = ref(false)
const visibleSteps = computed(() => props.steps.slice(0, 10))
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
        </div>
      </div>
    </aside>
  </div>
</template>
