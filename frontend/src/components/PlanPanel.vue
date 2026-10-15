<template>
  <div class="plan" v-if="todos.length">
    <div class="plan-title">任务计划</div>
    <ul>
      <li v-for="(t, i) in todos" :key="i">
        <span class="plan-status" :class="statusClass(t.status)">
          {{ statusIcon(t.status) }}
        </span>
        <span class="plan-content">{{ t.content }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
defineProps({ todos: { type: Array, default: () => [] } })

function statusClass(s) {
  return s === 'completed' ? 'done' : s === 'in_progress' ? 'doing' : 'pending'
}
function statusIcon(s) {
  return s === 'completed' ? '✓' : s === 'in_progress' ? '▶' : '○'
}
</script>

<style scoped>
.plan {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
}
.plan-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--muted);
}
.plan ul { list-style: none; margin: 0; padding: 0; }
.plan li { display: flex; gap: 8px; padding: 3px 0; align-items: baseline; }
.plan-status { width: 16px; text-align: center; }
.done { color: var(--success); }
.doing { color: var(--warning); }
.pending { color: var(--muted); }
.plan-content { flex: 1; }
.done + .plan-content, li:has(.done) .plan-content {
  text-decoration: line-through;
  color: var(--muted);
}
</style>
