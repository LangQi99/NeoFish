<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronRight, Brain } from 'lucide-vue-next'

interface Step {
  type: 'thinking' | 'tool'
  content: string
  completed: boolean
}

const props = defineProps<{
  steps: Step[]
  isActive: boolean
}>()

const { t } = useI18n()
const expanded = ref(false)

const currentStep = computed(() => {
  if (props.steps.length === 0) return null
  return props.steps[props.steps.length - 1]
})

const completedCount = computed(() => {
  return props.steps.filter(s => s.completed).length
})

const summaryText = computed(() => {
  if (props.isActive && currentStep.value) {
    return currentStep.value.content
  }
  return t('thinking.completed', { count: completedCount.value })
})

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="theme-card-soft thinking-chain overflow-hidden rounded-xl">
    <button
      @click="toggle"
      class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--surface-muted)]"
    >
      <div class="theme-button-strong flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full">
        <Brain :size="14" />
      </div>
      
      <span class="theme-text-secondary flex-1 truncate text-sm">
        {{ summaryText }}
      </span>
      
      <span v-if="!isActive" class="theme-text-muted mr-2 text-xs">
        {{ completedCount }} {{ $t('thinking.steps') }}
      </span>
      
      <ChevronRight v-if="!expanded" :size="16" class="theme-text-muted" />
      <ChevronDown v-else :size="16" class="theme-text-muted" />
    </button>
    
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      leave-active-class="transition-all duration-150 ease-in"
      enter-from-class="opacity-0 max-h-0"
      leave-to-class="opacity-0 max-h-0"
    >
      <div v-if="expanded" class="overflow-hidden border-t" style="max-height: 400px; border-color: var(--border-muted);">
        <div class="px-4 py-3 space-y-2">
          <div
            v-for="(step, idx) in steps"
            :key="idx"
            class="flex items-center gap-2 text-sm"
            :class="step.completed ? 'theme-text-muted' : 'theme-text-primary'"
          >
            <span v-if="step.completed" class="text-green-500">✓</span>
            <span v-else class="theme-text-muted">○</span>
            <span>{{ step.content }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
