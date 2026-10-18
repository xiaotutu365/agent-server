# thread-title 修复清单

- [x] 1. 复现：浏览器切会话，确认顶栏标题恒为「新对话」（bug.md 证据）
- [x] 2. 定位：currentThreadTitle 用 `x.id` 匹配，接口字段实为 `thread_id`
- [x] 3. 修复：ChatView.vue `x.id` → `x.thread_id`（1 行）
- [x] 4. 回归测试：前端无测试框架（无 vitest/jest），无法落自动化回归用例——以浏览器端到端验证替代，并在 fix.md 记录该缺口（如需自动化，需引入 vitest，另行评审）
- [x] 5. 端到端验证：切会话标题跟随、新会话显示「新对话」、刷新后标题正确
- [x] 6. fix.md 记录根因/改动/验证
