<template>
  <div class="msg" :class="msg.role">
    <div class="avatar">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
    <div class="body">
      <template v-if="msg.role === 'assistant'">
        <PlanPanel :todos="msg.plan" />
        <ToolSteps :steps="msg.steps" />
      </template>
      <div v-if="msg.content" class="content markdown" v-html="renderMarkdown(msg.content)"></div>
      <div v-else-if="msg.role === 'assistant' && msg.streaming" class="typing">思考中…</div>
      <div v-if="msg.error" class="error">⚠ {{ msg.error }}</div>
    </div>
  </div>
</template>

<script setup>
import { renderMarkdown } from '../markdown'
import PlanPanel from './PlanPanel.vue'
import ToolSteps from './ToolSteps.vue'

defineProps({ msg: { type: Object, required: true } })
</script>

<style scoped>
.msg { display: flex; gap: 10px; margin-bottom: 14px; }
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
.typing { color: var(--muted); font-size: 13px; padding: 6px 2px; animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: 0.4; } }
.error { color: var(--destructive); font-size: 13px; margin-top: 6px; }
</style>
