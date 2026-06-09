<script setup lang="ts">
import React from 'react'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createRoot, type Root } from 'react-dom/client'
import OpenUIMessage from './OpenUIMessage'

const props = defineProps<{
  content: string
  isStreaming?: boolean
}>()

const emit = defineEmits<{
  (e: 'action', message: string): void
}>()

const host = ref<HTMLElement | null>(null)
let root: Root | null = null

function renderOpenUI() {
  if (!host.value) return
  if (!root) {
    root = createRoot(host.value)
  }
  root.render(React.createElement(OpenUIMessage, {
    content: props.content,
    isStreaming: props.isStreaming,
    onAction: (message: string) => emit('action', message),
  }))
}

onMounted(renderOpenUI)
watch(() => [props.content, props.isStreaming], renderOpenUI)

onBeforeUnmount(() => {
  root?.unmount()
  root = null
})
</script>

<template>
  <div ref="host" class="openui-renderer"></div>
</template>
