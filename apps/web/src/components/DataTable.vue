<script setup lang="ts">
export type DataColumn = { key: string; label: string };

withDefaults(defineProps<{ columns: DataColumn[]; items: Record<string, unknown>[]; rowKey?: string; emptyText?: string }>(), {
  rowKey: "id",
  emptyText: "No records found.",
});
defineEmits<{ select: [item: Record<string, unknown>] }>();
</script>

<template>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead><tr><th v-for="column in columns" :key="column.key">{{ column.label }}</th></tr></thead>
      <tbody>
        <tr v-for="item in items" :key="String(item[rowKey])" tabindex="0" @click="$emit('select', item)" @keydown.enter="$emit('select', item)">
          <td v-for="column in columns" :key="column.key">{{ item[column.key] ?? "—" }}</td>
        </tr>
        <tr v-if="items.length === 0"><td :colspan="columns.length" class="data-table-empty">{{ emptyText }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
