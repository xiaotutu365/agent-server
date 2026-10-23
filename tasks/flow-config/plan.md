# Plan: flow-config M1 后端内核

Spec: docs/specs/SPEC-flow-config.md ｜ Intent: docs/intent/flow-config.md

## 架构要点

- 新模块 `backend/flow/`：`store.py`（flows/flow_runs 两表 CRUD）、`dsl.py`（definition 校验）、`runner.py`（动态 StateGraph 构建 + 执行 + resume）
- API 挂 FastAPI router（仿 kb/api.py 模式），require_admin 管流程 CRUD；发起/审批/查询需登录（get_current_user）
- thread_id = `flow:{run_id}`，复用全局 checkpointer/store 构建模式（仿 deep_agent.build_agent）
- llm 节点复用 main.get_agent_for 的缓存构建 → runner 需要接收 agent 工厂（依赖注入，避免循环 import）
- 人审：节点内 `interrupt(payload)`；resume 走 `Command(resume=decisions)`，与聊天 HITL 同协议
- 红线：LLM/工具调用不得阻塞事件循环（asyncio.to_thread 包同步工具）

## 执行顺序（TDD，红→绿→重构）

1. T1 store 层 → 2. T2 dsl 校验 → 3. T3 runner（3a 线性+插值+条件 → 3b 人审+resume）→ 4. T4 API → 5. T5 接线冒烟

## Checkpoints

- CP1（T1-T3 后）：单测全绿，runner 在无 LLM 依赖下可测（fake agent 工厂）
- CP2（T4-T5 后）：全量 pytest + curl SSE 端到端（fake/真实 LLM 各一）+ 向用户汇报

---

# M2 前端（spec 3.5）

## 架构要点

- API 封装层 `frontend/src/api/flows.js`（仿 api/kb.js 模式，复用 auth.js 的 apiFetch；SSE 用 GET /api/flow-runs/{id}/stream + fetch ReadableStream 解析，仿 api/chat.js 的帧解析）
- 管理页 `views/FlowView.vue`：流程列表（name/version/更新时间）+ 新建/编辑弹窗（name + definition JSON textarea，前端 JSON.parse 合法性校验 + 后端 400 detail 展示）+ 删除 + 「发起运行」跳转；路由 `/admin/flows`，AdminLayout groups 加导航项
- 运行页 `views/FlowRunView.vue`：发起（选流程 + 输入 JSON）→ 实例列表（状态徽章/当前节点）→ 实例详情：SSE 节点时间线（flow_step/flow_status 事件）+ 人审面板（pending 的 HITLRequest 展示 prompt，批准/拒绝+意见 → POST resume，复用聊天 decisions[] 协议）+ 取消按钮；路由 `/flows`（登录用户可进，非 admin 也可审批）
- 人审数据结构对齐 ChatView respondInterrupt 的 HITLResponse（实现时先读 ChatView.vue L461-617 确认 payload 形状）

## 执行顺序（垂直切片）

1. T6 api/flows.js + FlowView 管理页（列表/编辑/校验/删除）——完整「管理员配置流程」路径
2. T7 FlowRunView 运行页（发起/实例列表/SSE 时间线）——完整「发起并看进度」路径
3. T8 人审交互（pending 展示 + resume + 取消）——完整「审批闭环」路径
4. T9 浏览器端到端验收 + 全量测试回归

## Checkpoints

- CP3（T6 后）：可在页面上完成流程 CRUD，非法 JSON 被拦截
- CP4（T7-T8 后）：页面发起→SSE 逐节点可见→人审批准/拒绝→done/回环，全链路浏览器实测
- CP5（T9）：后端全量 pytest 绿 + 向用户汇报 M2 完成
