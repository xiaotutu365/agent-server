<template>
  <div class="msg" :class="msg.role" :aria-busy="msg.role === 'assistant' && msg.streaming ? 'true' : undefined">
    <div class="avatar" aria-hidden="true">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
    <div class="body">
      <template v-if="msg.role === 'assistant'">
        <PlanPanel :todos="msg.plan" />
        <ToolSteps :steps="msg.steps" />
      </template>
      <div v-if="msg.content" class="content markdown" v-html="renderMarkdown(msg.content)"></div>
      <div v-if="msg.citations && msg.citations.length" class="citations" aria-label="引用来源">
        <span class="citations-label">来源</span>
        <button
          v-for="(c, i) in msg.citations" :key="i"
          class="badge citation citation-btn"
          :title="`查看 ${c.file} #${(c.chunk_idx ?? 0) + 1} 原文`"
          @click="openChunk(c)"
        >
          {{ c.file }} #{{ (c.chunk_idx ?? 0) + 1 }}
        </button>
      </div>
      <div
        v-if="!msg.content && msg.role === 'assistant' && msg.streaming"
        class="typing"
        role="status"
        aria-label="正在生成回复"
      >
        <span class="dot" v-for="n in 3" :key="n"></span>
        <span class="typing-text">思考中…</span>
      </div>
      <div v-if="msg.error" class="error-card" role="alert">
        <span class="error-text">⚠ {{ msg.error }}</span>
        <button
          v-if="!msg.streaming"
          class="error-retry"
          @click="$emit('retry')"
        >重试</button>
      </div>
    </div>

    <div v-if="chunkModal.open" class="chunk-mask" @click.self="closeChunk">
      <div class="chunk-modal" role="dialog" aria-modal="true" aria-label="引用片段原文">
        <div class="chunk-head">
          <span class="chunk-title">引用原文</span>
          <button class="chunk-close" aria-label="关闭" @click="closeChunk">×</button>
        </div>
        <div class="chunk-meta">
          <span>{{ chunkModal.source }}</span>
          <span>片段 #{{ chunkModal.chunkIdx + 1 }}</span>
          <span v-if="chunkModal.score != null">RRF {{ Number(chunkModal.score).toFixed(4) }}</span>
        </div>
        <div class="chunk-body">
          <p v-if="chunkModal.loading" class="chunk-state">加载中…</p>
          <p v-else-if="chunkModal.error" class="chunk-state chunk-err">{{ chunkModal.error }}</p>
          <pre v-else class="chunk-text">{{ chunkModal.text }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '../markdown'
import PlanPanel from './PlanPanel.vue'
import ToolSteps from './ToolSteps.vue'
import { getChunk } from '../api/kb'

defineProps({ msg: { type: Object, required: true } })
defineEmits(['retry'])

const chunkModal = reactive({ open: false, loading: false, error: '', text: '', source: '', chunkIdx: 0, score: null })

async function openChunk(c) {
  chunkModal.open = true
  chunkModal.loading = true
  chunkModal.error = ''
  chunkModal.text = ''
  chunkModal.source = c.file
  chunkModal.chunkIdx = c.chunk_idx ?? 0
  chunkModal.score = c.score
  try {
    const data = await getChunk(c.kb_id, c.file, c.chunk_idx ?? 0)
    chunkModal.text = data.text || '（片段为空）'
  } catch (e) {
    chunkModal.error = e.message || '加载失败'
  } finally {
    chunkModal.loading = false
  }
}

function closeChunk() { chunkModal.open = false }

function onKeydown(e) { if (e.key === 'Escape') closeChunk() }
window.addEventListener('keydown', onKeydown)
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.msg { display: flex; gap: 10px; margin-bottom: 14px; }
.citations { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.citations-label { font-size: 12px; color: var(--muted); font-weight: 600; }
.citation { font-size: 11px; }
.citation-btn {
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}
.citation-btn:hover { border-color: var(--accent); color: var(--accent); }

/* 引用原文模态 */
.chunk-mask {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(0, 0, 0, .45);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.chunk-modal {
  background: var(--panel, #fff); color: var(--text);
  border: 1px solid var(--border); border-radius: 12px;
  width: 100%; max-width: 640px; max-height: 75vh;
  display: flex; flex-direction: column;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .18);
}
.chunk-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.chunk-title { font-weight: 600; font-size: 14px; }
.chunk-close {
  border: none; background: transparent; color: var(--muted);
  font-size: 20px; line-height: 1; cursor: pointer; padding: 2px 6px;
  border-radius: 6px;
}
.chunk-close:hover { background: color-mix(in srgb, var(--muted) 15%, transparent); }
.chunk-meta {
  display: flex; gap: 12px; flex-wrap: wrap;
  padding: 10px 16px; font-size: 12px; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
.chunk-body { padding: 14px 16px; overflow: auto; }
.chunk-state { color: var(--muted); font-size: 13px; }
.chunk-err { color: var(--destructive); }
.chunk-text {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-size: 13px; line-height: 1.7;
  font-family: inherit;
}
.msg.user { flex-direction: row-reverse; }
.avatar {
  flex: none; width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #fff;
  background: var(--accent);
}
.msg.user .avatar { background: #6b7280; }
.body { max-width: 82%; min-width: 0; }
.msg.user .body {
  background: var(--user-bubble); color: var(--text);
  padding: 8px 12px; border: 1px solid var(--border); border-radius: 14px 14px 4px 14px;
  white-space: pre-wrap; word-break: break-word;
}
.msg.assistant .body { width: 100%; max-width: 100%; }
.content {
  background: var(--assistant-bubble);
  padding: 9px 14px; border-radius: 14px 14px 14px 4px;
  border: 1px solid var(--border);
  line-height: 1.5; word-break: break-word;
}
/* 用户气泡由 .body 绘制，内层 .content 不再叠加盒子（否则内边距翻倍、气泡过高） */
.msg.user .content {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
}
/* 气泡内边距已提供间距，去掉首尾块的默认外边距，避免顶部/底部多余空白 */
.content.markdown > :first-child { margin-top: 0; }
.content.markdown > :last-child { margin-bottom: 0; }
.typing {
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--muted); font-size: 13px; padding: 8px 2px;
}
.typing .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--muted);
  animation: bounce 1.2s ease-in-out infinite;
}
.typing .dot:nth-child(2) { animation-delay: 0.15s; }
.typing .dot:nth-child(3) { animation-delay: 0.3s; }
.typing-text { margin-left: 4px; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-4px); opacity: 1; }
}
.error-card {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 6px;
  padding: 9px 12px;
  background: color-mix(in srgb, var(--destructive) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  border-radius: 10px;
  color: var(--destructive); font-size: 13px;
}
.error-text { flex: 1; min-width: 0; word-break: break-word; }
.error-retry {
  flex: none;
  border: 1px solid var(--destructive); background: transparent; color: var(--destructive);
  border-radius: 8px; padding: 4px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
  transition: background-color .15s ease;
}
.error-retry:hover { background: color-mix(in srgb, var(--destructive) 12%, transparent); }
</style>
