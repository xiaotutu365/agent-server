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
