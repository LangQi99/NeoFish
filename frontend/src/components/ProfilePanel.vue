<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

export interface ProfileField {
  key: string
  label: string
  default: string
}

const props = defineProps<{
  fields: ProfileField[]
  currentProfile: Record<string, string>
}>()

const emit = defineEmits<{
  save: [profile: Record<string, string>]
}>()

const { t } = useI18n()

const form = ref<Record<string, string>>({})
const editing = ref(false)
const submitting = ref(false)

function initForm() {
  props.fields.forEach(f => {
    form.value[f.key] = props.currentProfile[f.key] || f.default || ''
  })
}

onMounted(initForm)

const isFormValid = computed(() => {
  const name = (form.value.name || '').trim()
  return name.length > 0
})

const hasProfile = computed(() => {
  return Object.values(props.currentProfile).some(v => (v || '').trim())
})

function fieldLabel(key: string, defaultLabel: string): string {
  const i18nKey = `profile.fields.${key}`
  const translated = t(i18nKey)
  return translated === i18nKey ? defaultLabel : translated
}

function startEdit() {
  initForm()
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function handleSave() {
  if (!isFormValid.value || submitting.value) return
  submitting.value = true
  const profile: Record<string, string> = {}
  props.fields.forEach(f => {
    profile[f.key] = (form.value[f.key] || '').trim()
  })
  emit('save', profile)
  editing.value = false
  submitting.value = false
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-5 py-4 border-b" style="border-color: var(--border-muted);">
      <h3 class="text-sm font-semibold tracking-wide" style="color: var(--text-primary);">
        {{ $t('profile.panel_title') }}
      </h3>
      <button
        v-if="hasProfile && !editing"
        @click="startEdit"
        class="rounded-lg px-3 py-1 text-xs font-medium transition-colors"
        style="color: var(--text-secondary); background: var(--surface-soft);"
      >
        {{ $t('profile.edit') }}
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-5 py-4 theme-scrollbar">
      <!-- View mode -->
      <div v-if="hasProfile && !editing" class="space-y-3">
        <div v-for="field in fields" :key="field.key" class="flex flex-col gap-0.5">
          <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: var(--text-muted);">
            {{ fieldLabel(field.key, field.label) }}
          </span>
          <span class="text-sm" style="color: var(--text-primary);">
            {{ currentProfile[field.key] || '—' }}
          </span>
        </div>
      </div>

      <!-- Empty / Edit mode -->
      <div v-else class="space-y-4">
        <p v-if="!hasProfile" class="text-sm leading-relaxed" style="color: var(--text-muted);">
          {{ $t('profile.panel_hint') }}
        </p>

        <div v-for="field in fields" :key="field.key" class="flex flex-col gap-1">
          <label class="text-[10px] font-semibold uppercase tracking-wider" style="color: var(--text-muted);">
            {{ fieldLabel(field.key, field.label) }}
          </label>
          <input
            v-if="field.key !== 'bio'"
            v-model="form[field.key]"
            class="theme-input-shell rounded-lg px-3 py-2 text-sm transition-colors outline-none"
            style="color: var(--text-primary);"
            :placeholder="fieldLabel(field.key, field.label)"
            autocomplete="off"
          />
          <textarea
            v-else
            v-model="form[field.key]"
            class="theme-input-shell rounded-lg px-3 py-2 text-sm transition-colors outline-none resize-none"
            style="color: var(--text-primary); min-height: 4rem;"
            :placeholder="fieldLabel(field.key, field.label)"
            autocomplete="off"
          ></textarea>
        </div>
      </div>
    </div>

    <!-- Actions (edit mode only) -->
    <div v-if="!hasProfile || editing" class="border-t px-5 py-4 space-y-2" style="border-color: var(--border-muted);">
      <button
        @click="handleSave"
        :disabled="!isFormValid || submitting"
        class="w-full rounded-xl py-2.5 text-sm font-semibold transition-all duration-200 active:scale-[0.98]"
        :class="isFormValid && !submitting
          ? 'text-white shadow-lg'
          : 'cursor-not-allowed opacity-40'"
        style="background: var(--surface-strong); color: var(--text-contrast);"
      >
        {{ submitting ? $t('profile.saving') : $t('profile.save') }}
      </button>
      <button
        v-if="hasProfile"
        @click="cancelEdit"
        class="w-full rounded-xl py-2 text-xs font-medium transition-colors theme-button-soft"
      >
        {{ $t('profile.cancel') }}
      </button>
    </div>
  </div>
</template>
