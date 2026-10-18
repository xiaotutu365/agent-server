# Bug：顶栏会话标题恒显示「新对话」

- 发现时间：2026-10-18（session-model-select 冒烟期间）
- 发现途径：浏览器快照 + evaluate 实测（当前会话为 travel 线程，顶栏仍显示「新对话」）
- 引入提交：1d942e5（feat(chat): 聊天窗口 EvoFlow 改版）新增的 `currentThreadTitle` computed

## 现象

聊天页顶栏标题（`.chat-title`）无论切到哪个已有会话，始终显示「新对话」。

## 复现步骤

1. 打开 http://localhost:5173/#/，左侧点击任意已有会话
2. 观察顶栏标题 → 仍为「新对话」，不显示该会话的首条消息标题

## 证据

- `/api/threads` 返回字段为 `thread_id`（backend/main.py list_threads）
- ChatView.vue `currentThreadTitle` 用 `threads.value.find((x) => x.id === threadId.value)` 匹配
  → `x.id` 不存在，find 恒为 undefined → 兜底返回「新对话」
- 实测 evaluate：`chatTitle: "新对话"`，而 lastThreadId 指向存在的会话

## 影响

仅展示问题：会话切换、消息恢复、模型覆盖回显均正常，仅标题不更新。
