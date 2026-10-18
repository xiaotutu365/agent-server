# Intent: 流程配置（LangGraph Flow）

> interview-me 产出，2026-10-18 经用户逐条确认。

- **Outcome**：在 agent-server 上可配置地运行「多步骤 + 人在中间把关」的业务流程：步骤由 LLM 节点/工具节点执行，关键节点暂停等人批准/给意见后继续。
- **User**：用户自己先配置使用（管理员），后续可开放给普通用户发起流程。
- **Why now**：聊天是自由发挥，重复性业务需要固定步骤 + 质量把关，人审点保证 LLM 输出可控。
- **Success**：在后台配置一条含人审节点的流程 → 发起 → 自动跑到人审点暂停 → 审批后继续跑完 → 全程进度可见。
- **Constraint**：复用现有资产——Agent 缓存构建、HITL interrupt、checkpointer 持久化、SSE 协议、hitl-panel 前端组件；不引入消息队列/新存储。
- **Out of scope**：拖拽式流程画布（首期 JSON 编辑）、并行/子图嵌套、定时触发、多人协作审批、流程市场/模板库。
- **待补**：第一个真实业务流程场景（spec 示例节点先占位，用户提供后替换）。

技术方向讨论中确立的候选路线：deepagents subagents 配置化 / LangGraph StateGraph 流程 DSL / 扩展现有多角色流水线；因「确定性步骤 + 人审门」的诉求选定 **StateGraph 流程 DSL（方案 B）**。
