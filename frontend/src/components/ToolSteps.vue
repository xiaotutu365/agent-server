<template>
  <div class="steps">
    <div v-for="(s, i) in steps" :key="i" class="step" :class="{ running: s.status === 'running' }">
      <button
        class="step-head"
        @click="s.open = !s.open"
        :aria-expanded="s.open ? 'true' : 'false'"
        :aria-controls="`step-body-${i}`"
      >
        <span class="step-icon" :class="s.status" aria-hidden="true">{{ s.status === 'running' ? '⟳' : '✓' }}</span>
        <span class="step-tool">{{ s.tool }}</span>
        <span class="step-status" :class="s.status">{{ s.status === 'running' ? '运行中' : '已完成' }}</span>
        <span class="step-chevron" aria-hidden="true">{{ s.open ? '▾' : '▸' }}</span>
      </button>
      <div v-if="s.open" :id="`step-body-${i}`" class="step-body">
        <div class="step-label">输入</div>
        <pre>{{ s.input }}</pre>
        <template v-if="s.output">
          <div class="step-label">输出</div>
          <pre>{{ s.output }}</pre>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ steps: { type: Array, default: () => [] } })
</script>

<style scoped>
.steps { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.step {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  font-size: 13px;
  overflow: hidden;
}
.step.running { border-color: color-mix(in srgb, var(--warning) 45%, var(--border)); }
.step-head {
  display: flex; align-items: center; gap: 8px;
  width: 100%; border: none; background: transparent;
  padding: 7px 12px; cursor: pointer; user-select: none;
  font-family: inherit; font-size: 13px; color: var(--text); text-align: left;
}
.step-head:hover { background: var(--panel-hover); }
.step-icon { width: 16px; text-align: center; flex: none; }
.step-icon.running { color: var(--warning); animation: spin 1.2s linear infinite; display: inline-block; }
.step-icon.done { color: var(--success); }
@keyframes spin { to { transform: rotate(360deg); } }
/* 工具名徽章：等宽字体 + 药丸底色，EvoFlow 命令日志风格 */
.step-tool {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--muted) 12%, transparent);
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step-status { font-size: 12px; flex: none; }
.step-status.running { color: var(--warning); }
.step-status.done { color: var(--muted); }
.step-chevron { margin-left: auto; color: var(--muted); font-size: 12px; flex: none; }
.step-body { padding: 0 12px 10px; }
.step-label { color: var(--muted); font-size: 12px; margin: 6px 0 3px; }
.step-body pre {
  margin: 0; padding: 8px 10px; background: var(--code-bg);
  border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  border-radius: 8px; white-space: pre-wrap; word-break: break-all;
  font-family: var(--mono); font-size: 12px; line-height: 1.55;
  max-height: 220px; overflow: auto;
}
</style>
