<template>
  <div class="plan" v-if="todos.length">
    <div class="plan-head">
      <span class="plan-title">任务清单</span>
      <span class="plan-count" v-if="doneCount">{{ doneCount }}/{{ todos.length }}</span>
    </div>
    <div class="plan-progress" aria-hidden="true">
      <div class="bar"><div class="bar-fill" :style="{ width: pct + '%' }"></div></div>
    </div>
    <ul>
      <li v-for="(t, i) in todos" :key="i" :class="statusClass(t.status)">
        <span class="plan-status" :class="statusClass(t.status)" aria-hidden="true">
          <template v-if="t.status === 'completed'">✓</template>
          <template v-else-if="t.status === 'in_progress'">▶</template>
          <template v-else>○</template>
        </span>
        <span class="plan-content">{{ t.content }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ todos: { type: Array, default: () => [] } })

// 仅展示：清单由 agent 的 write_todos 驱动，用户不可勾选（SPEC C1.1）
const doneCount = computed(() => props.todos.filter((t) => t.status === 'completed').length)
const pct = computed(() =>
  props.todos.length ? Math.round((doneCount.value / props.todos.length) * 100) : 0,
)

function statusClass(s) {
  return s === 'completed' ? 'done' : s === 'in_progress' ? 'doing' : 'pending'
}
</script>

<style scoped>
.plan {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  padding: 10px 14px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.plan-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.plan-title {
  font-weight: 600;
  color: var(--text);
  font-size: 13px;
}
.plan-count {
  font-size: 12px;
  color: var(--muted);
  background: var(--panel-hover, color-mix(in srgb, var(--muted) 12%, transparent));
  border-radius: 999px;
  padding: 1px 8px;
}
.plan-progress { padding: 8px 0 4px; }
.bar {
  height: 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 18%, transparent);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.3s ease;
}
.plan ul { list-style: none; margin: 0; padding: 0; }
.plan li { display: flex; gap: 8px; padding: 4px 0; align-items: baseline; }
.plan-status { width: 16px; text-align: center; flex: none; }
.plan-status.done { color: var(--success); }
.plan-status.doing { color: var(--warning); animation: pulse 1.4s ease-in-out infinite; display: inline-block; }
.plan-status.pending { color: var(--muted); }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.plan-content { flex: 1; min-width: 0; word-break: break-word; }
li.done .plan-content {
  text-decoration: line-through;
  color: var(--muted);
}
</style>
