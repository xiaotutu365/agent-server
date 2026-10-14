# Spec: 人机交互（Human-in-the-Loop, HITL）子系统（AgentServer）

> 状态：实现中（Phase 2 计划已确认，集中配置项 `INTERRUPT_TOOLS` 待你最终决定呈现哪些）。
> 技能：`spec-driven-development`。模块 id：`hitl`。
> 依赖：`deepagents` 内置 `HumanInTheLoopMiddleware`（`langchain.agents.middleware`）+ LangGraph `interrupt()` / `Command(resume=...)`。

---

## Objective（目标）

给现有 Deep Agent Server 增加**人机交互（HITL）**能力：当 agent 在长任务执行途中需要用户确认或补充信息，能够**暂停并等待用户回复**，再继续往下走。

覆盖两类场景（统一用同一套机制）：

1. **业务操作确认**：agent 准备执行写操作类工具（如 `create_work_order`）前，先问用户"确认执行吗？"——用户可 `approve` / `reject`（必要时 `edit` 改参数）。
2. **主动提问**：agent 在任务中途缺信息时，调用 `ask_human(question)` 主动问用户一个问题——用户用 `respond` 直接回答，回答作为该工具的返回结果继续驱动 agent。

---

## 设计要点

`deepagents` 的 `create_deep_agent` 原生支持 `interrupt_on` 参数，底层自动装配 `HumanInTheLoopMiddleware`：

- 模型产出工具调用后、实际执行前，命中 `interrupt_on` 的工具会触发 `interrupt(hitl_request)`，图**挂起**并保留 checkpoint（现有 SQLite checkpointer 已支持）。
- 挂起时后端收到 `on_interrupt` 事件（LangGraph 1.2.x），其 `data.interrupts[].value` 为 `HITLRequest`：`{action_requests, review_configs}`。
- 前端把 `HITLRequest` 渲染成确认/回复面板；用户决策后经 `POST /api/chat/stream` 带 `resume` 字段提交，后端用 `Command(resume={"decisions": [...]})` 恢复图。
- 四种决策（`DecisionType`）：
  - `approve`：批准执行（用于业务确认）
  - `reject`：拒绝，可选 `message` 理由
  - `respond`：代替工具返回（用于"向用户提问"类工具，用户的回答即工具返回值）
  - `edit`：修改工具 `args` 后执行

### 集中配置（待你最终决定呈现哪些）

所有"需要人工介入"的工具集中在 `backend/agent/deep_agent.py` 的 `INTERRUPT_TOOLS` 字典：

```python
INTERRUPT_TOOLS: dict[str, dict] = {
    # 业务写操作：执行前需用户确认
    "create_work_order": {"allowed_decisions": ["approve", "reject"]},
    # 主动提问类工具：由用户回答代替执行
    "ask_human": {"allowed_decisions": ["respond"]},
}
```

- 增删工具、调整 `allowed_decisions` 即可决定"哪些呈现给用户"，**无需改其他代码**。
- `allowed_decisions` 可选值：`approve` / `reject` / `respond` / `edit`。

---

## 涉及文件

| 文件 | 改动 |
|---|---|
| `backend/agent/human_tools.py` | 新增 `ask_human` 工具（HUMAN_TOOLS） |
| `backend/agent/deep_agent.py` | 注册 `HUMAN_TOOLS`；定义 `INTERRUPT_TOOLS`；`create_deep_agent(interrupt_on=INTERRUPT_TOOLS)` |
| `backend/main.py` | `ChatRequest` 增 `resume`；`event_gen` 捕获 `on_interrupt` 发 SSE `interrupt` 事件并 `break`；`resume` 时用 `Command(resume=...)` 恢复 |
| `frontend/src/api/chat.js` | `dispatch` 处理 `interrupt`；`streamChat` 支持 `resume` 参数 |
| `frontend/src/views/ChatView.vue` | 渲染中断确认/回复面板；提交决策走 resume 流，追加到当前 assistant 消息 |

---

## SSE 事件新增

| event | data | 含义 |
|---|---|---|
| `interrupt` | `{"requests": [HITLRequest, ...]}` | 图挂起，等待用户决策。`HITLRequest` 含 `action_requests`（`name`/`args`/`description`）与 `review_configs`（`action_name`/`allowed_decisions`） |

## API 变更

`POST /api/chat/stream` 请求体新增可选字段：

```json
{ "message": "", "thread_id": "t1", "user_id": "default",
  "resume": { "decisions": [ {"type": "approve"} ] } }
```

- 普通新消息：带 `message`（或空），不带 `resume`。
- 恢复中断：带 `resume`（HITLResponse），`message` 可省略。
- `resume` 与 `thread_id` 必须对应同一挂起会话（checkpointer 恢复断点）。

---

## 测试策略

- 单元/集成（pytest，mock 模型与 CRM）：
  - `test_hitl_config.py`：验证 `INTERRUPT_TOOLS` 工具确实被 `HumanInTheLoopMiddleware` 拦截（构造图、`ainvoke` 后 `aget_state().interrupts` 非空）。
  - `test_hitl_resume.py`：模拟 `approve`/`reject`/`respond` 三种 `Command(resume=...)`，验证图恢复后行为正确（执行/跳过/以回答替代）。
- 手动冒烟：前端发起会触发 `create_work_order` 的请求 → 看到确认面板 → 批准/拒绝 → 流继续或终止；发起会触发 `ask_human` 的请求 → 看到提问面板 → 回答 → agent 继续。

---

## Boundaries

**Always**
- 中断状态必须经 checkpointer 持久化，刷新/重连后可恢复。
- 恢复请求必须携带与中断一致的 `thread_id`（及 `user_id`）。

**Ask first**
- 把新工具加入 `INTERRUPT_TOOLS`（即"呈现给用户确认"）属行为变更，需在 `INTERRUPT_TOOLS` 显式声明。

**Never**
- 在 `interrupt_on` 配置为需要确认的工具上，绕过确认直接执行。
- 把普通只读查询（如 `query_customer`、`web_search`）默认加入中断（会严重拖慢体验）。
