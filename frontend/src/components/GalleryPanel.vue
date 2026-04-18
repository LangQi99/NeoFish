<script setup lang="ts">
import { ImagePlus } from 'lucide-vue-next'
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="border-b px-3 py-4" style="border-color: var(--border-muted);">
      <h2 class="theme-text-muted text-xs font-semibold uppercase tracking-widest">
        {{ $t('gallery.title') }}
      </h2>
    </div>
    <div class="theme-text-muted flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
      <ImagePlus :size="24" />
      <p class="text-xs leading-5">{{ $t('gallery.placeholder') }}</p>
    </div>
  </div>
</template>
