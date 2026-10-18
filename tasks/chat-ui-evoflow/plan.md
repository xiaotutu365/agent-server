# Plan：聊天窗口 EvoFlow 风格改版

- spec：[docs/specs/SPEC-chat-ui-evoflow.md](../docs/specs/SPEC-chat-ui-evoflow.md)
- 策略：垂直切片，每个任务交付一个可验证的完整行为；T3/T4 同文件顺序执行
- 测试：后端 TDD（上传接口）；前端构建 + 浏览器实测；最后统一回归 + review

## 任务序列

| # | 任务 | 尺寸 | 依赖 | 涉及文件 |
|---|---|---|---|---|
| T1 | 上传接口 POST /api/chat/upload（TDD） | S | - | backend/main.py, backend/tests/test_chat_upload.py |
| T2 | PlanPanel/ToolSteps EvoFlow 视觉重做 | M | - | frontend/src/components/PlanPanel.vue, ToolSteps.vue |
| T3 | 顶部标题栏改版 + task-panel 移除 | M | - | frontend/src/views/ChatView.vue |
| T4 | composer 改版（+上传 / 深度思考占位） | M | T1 | frontend/src/views/ChatView.vue, frontend/src/api/chat.js |
| T5 | ThreadList 微调 + 暗色主题同步 + 构建 | S | T2-T4 | frontend/src/components/ThreadList.vue, style.css |

## Checkpoint

- CP1（T1 后）：pytest 全绿，上传接口 curl 冒烟通过
- CP2（T2-T4 后）：npm run build 通过，浏览器实测消息流/标题栏/输入区新形态
- CP3（T5 后）：亮/暗主题检查、全功能回归、review

## 关键决策（来自 spec）

- 任务清单仅展示不可勾选（agent 的 write_todos 驱动）
- 深度思考纯占位，请求不带字段
- 上传存 workspace/uploads/，消息注入路径由 agent read_file 读取
- SSE 协议零变更
