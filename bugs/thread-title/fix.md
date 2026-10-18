# thread-title 修复记录

## 根因

ChatView.vue 的 `currentThreadTitle` computed 用 `threads.value.find((x) => x.id === threadId.value)` 匹配当前会话，
但 `GET /api/threads` 返回的会话对象字段是 `thread_id`（无 `id` 字段），find 永远匹配不上，
兜底分支 `|| '新对话'` 恒生效。该 computed 由 1d942e5（chat-ui-evoflow 顶栏改造）引入。

## 改动范围

- frontend/src/views/ChatView.vue：`x.id` → `x.thread_id`（1 行，currentThreadTitle 内）

## 回归测试

前端无测试框架（无 vitest/jest），本次以浏览器端到端验证替代；如需自动化回归需引入
vitest（新增依赖，须另行评审）。已验证场景：

1. 刷新恢复：lastThreadId 指向 travel 会话，顶栏显示「帮我规划一个三天的杭州旅行行程，并写入 travel.md」
2. 切换会话：点「我想出去旅游」→ 标题变「我想出去旅游」
3. 新建会话：标题回「新对话」，模型下拉同帧回「默认（跟随全局）」

## 验证结果

- 2026-10-18 浏览器实测：三场景全部符合预期
- `npm run build` 通过；后端无改动，pytest 全量 164 passed（拆分提交时验证）
