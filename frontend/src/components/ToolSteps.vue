<template>
  <div class="steps">
    <div v-for="(s, i) in steps" :key="i" class="step">
      <div class="step-head" @click="s.open = !s.open">
        <span class="step-icon" :class="s.status">{{ s.status === 'running' ? '⟳' : '✓' }}</span>
        <span class="step-tool">{{ s.tool }}</span>
        <span class="step-toggle">{{ s.open ? '收起' : '详情' }}</span>
      </div>
      <div v-if="s.open" class="step-body">
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
  border-radius: 8px;
  background: var(--panel);
  font-size: 13px;
  overflow: hidden;
}
.step-head {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; cursor: pointer; user-select: none;
}
.step-head:hover { background: var(--panel-hover); }
.step-icon { width: 16px; text-align: center; }
.step-icon.running { color: #e8930c; animation: spin 1.2s linear infinite; display: inline-block; }
.step-icon.done { color: var(--success); }
@keyframes spin { to { transform: rotate(360deg); } }
.step-tool { font-weight: 600; font-family: var(--mono); }
.step-toggle { margin-left: auto; color: var(--muted); font-size: 12px; }
.step-body { padding: 0 12px 10px; }
.step-label { color: var(--muted); font-size: 12px; margin: 6px 0 3px; }
.step-body pre {
  margin: 0; padding: 8px 10px; background: var(--code-bg);
  border-radius: 6px; white-space: pre-wrap; word-break: break-all;
  font-family: var(--mono); font-size: 12px; max-height: 200px; overflow: auto;
}
</style>
