<script setup lang="ts">
import { PlaySquare, Settings, Compass, LayoutGrid } from 'lucide-vue-next'
</script>

<template>
  <aside class="w-16 h-screen fixed left-0 top-0 flex flex-col items-center py-6 border-r border-neutral-200/50 bg-white/50 backdrop-blur-sm z-50">
    <!-- Top Icons -->
    <div class="flex flex-col gap-6">
      <button class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
        <Compass :size="20" stroke-width="2" />
      </button>
      <button class="p-2 rounded-xl text-neutral-800 bg-neutral-100 transition-colors">
        <LayoutGrid :size="20" stroke-width="2" />
      </button>
      <button class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
        <PlaySquare :size="20" stroke-width="2" />
      </button>
    </div>
    
    <div class="mt-auto">
      <button class="p-2 rounded-xl text-neutral-400 hover:text-neutral-800 hover:bg-neutral-100 transition-colors">
        <Settings :size="20" stroke-width="2" />
      </button>
    </div>
  </aside>
</template>
