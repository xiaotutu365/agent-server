<template>
  <aside class="sidebar">
    <button class="new-btn" @click="$emit('new')" :disabled="busy">＋ 新建会话</button>
    <div class="list">
      <div
        v-for="t in threads"
        :key="t.thread_id"
        class="item"
        :class="{ active: t.thread_id === currentId }"
        role="button"
        tabindex="0"
        :aria-current="t.thread_id === currentId ? 'true' : undefined"
        @click="$emit('select', t.thread_id)"
        @keydown.enter.prevent="$emit('select', t.thread_id)"
        @keydown.space.prevent="$emit('select', t.thread_id)"
      >
        <span class="item-title">{{ t.title || '新会话' }}</span>
        <span class="item-time" :title="absTime(t.updated_at)">{{ relTime(t.updated_at) }}</span>
        <button class="del" aria-label="删除会话" @click.stop="$emit('remove', t.thread_id)">×</button>
      </div>
      <div v-if="!threads.length" class="empty">暂无历史会话</div>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  threads: { type: Array, default: () => [] },
  currentId: { type: String, default: '' },
  busy: { type: Boolean, default: false }
})
defineEmits(['new', 'select', 'remove'])

// 会话条目相对时间（对齐 EvoFlow 需求图）：刚刚 / Xm / Xh / Xd / 超一周显示日期
function relTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 0) return ''
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function absTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? '' : d.toLocaleString()
}
</script>

<style scoped>
.sidebar {
  flex: none;
  width: 220px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--panel);
  padding: 12px;
  gap: 10px;
}
.new-btn {
  border: none;
  background: var(--accent);
  color: var(--on-primary);
  padding: 9px 0;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.new-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.item {
  display: flex; align-items: center; gap: 6px;
  padding: 9px 10px; border-radius: 10px; cursor: pointer;
  font-size: 13px; color: var(--text);
  transition: background-color .15s ease;
}
.item:hover { background: var(--panel-hover); }
.item.active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-weight: 600;
}
.item-title { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-time { flex: none; color: var(--muted); font-size: 11px; }
.del {
  flex: none; border: none; background: transparent; color: var(--muted);
  font-size: 16px; cursor: pointer; line-height: 1; padding: 2px 6px; border-radius: 5px;
  visibility: hidden;
}
.item:hover .del { visibility: visible; }
.item:focus-within .del { visibility: visible; }
.del:hover { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }
.empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px 0; }

@media (max-width: 760px) {
  .sidebar { width: 100%; max-height: 180px; border-right: 0; border-bottom: 1px solid var(--border); }
  .list { min-height: 0; }
  .del { visibility: visible; }
}
</style>
