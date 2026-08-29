<script setup lang="ts">
defineProps<{ name: string }>();
</script>

<template>
  <svg class="navigation-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'home'">
      <path d="m3 11 9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M9 20v-6h6v6" />
    </template>
    <template v-else-if="name === 'status'">
      <path d="M3 12h4l2-5 4 10 2-5h6" /><path d="M4 4h16v16H4z" />
    </template>
    <template v-else-if="name === 'cad'">
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" />
    </template>
    <template v-else-if="name === 'similarity'">
      <rect x="3" y="4" width="11" height="11" rx="2" /><rect x="10" y="9" width="11" height="11" rx="2" />
    </template>
    <template v-else-if="name === 'design_review'">
      <path d="M12 3 5 6v5c0 4.6 2.8 7.8 7 10 4.2-2.2 7-5.4 7-10V6z" /><path d="m9 12 2 2 4-4" />
    </template>
    <template v-else-if="name === 'process_trial'">
      <path d="M4 6h7M15 6h5M4 12h3M11 12h9M4 18h9M17 18h3" /><circle cx="13" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="15" cy="18" r="2" />
    </template>
    <template v-else-if="name === 'cae'">
      <path d="M4 19V5M4 19h16" /><path d="m7 15 4-4 3 2 5-6" />
    </template>
    <template v-else-if="name === 'hmi'">
      <rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4M7 9h3M7 12h7" />
    </template>
    <template v-else-if="name === 'knowledge'">
      <path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H12v17H7.5A3.5 3.5 0 0 0 4 22z" /><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H12v17h4.5A3.5 3.5 0 0 1 20 22z" />
    </template>
    <template v-else-if="name === 'identity'">
      <circle cx="9" cy="8" r="3" /><path d="M3.5 19c.8-3.2 2.7-5 5.5-5s4.7 1.8 5.5 5" /><path d="M16 8h5M18.5 5.5v5M16 15h5M16 19h5" />
    </template>
    <template v-else-if="name === 'master_data'">
      <ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" /><path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </template>
    <template v-else-if="name === 'mold_registry'">
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="M8 8h8M8 12h8M8 16h5" />
    </template>
    <template v-else>
      <path d="M7 3h10v4H7z" /><path d="M5 5H3v16h18V5h-2M8 12h8M8 16h5" />
    </template>
  </svg>
</template>
