# SPEC: 流程配置（flow-config）

> 背景与需求来源：[intent/flow-config.md](../intent/flow-config.md)。状态：**草案，待评审**。

## 1. 目标

让管理员通过 JSON 配置定义「多步骤 + 人审门」的业务流程（LangGraph StateGraph 动态构建），发起后自动执行、人审点暂停、审批后继续，全程 SSE 进度可见。

## 2. 非目标（Out of Scope）

拖拽画布、并行/子图、定时触发、多人协作审批、流程模板库、流程版本对比回滚。

## 3. 方案

### 3.1 数据模型

新表 `flows`（SQLite，与 agent_sessions.db 同库）：

```sql
CREATE TABLE IF NOT EXISTS flows (
  flow_id TEXT PRIMARY KEY,          -- uuid
  name TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  definition TEXT NOT NULL,          -- JSON DSL（第 3.2 节）
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

新表 `flow_runs`（流程实例）：

```sql
CREATE TABLE IF NOT EXISTS flow_runs (
  run_id TEXT PRIMARY KEY,           -- 同时作为 langgraph thread_id（前缀 flow:{run_id}）
  flow_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',  -- running/waiting_human/done/failed/cancelled
  current_node TEXT,
  input TEXT NOT NULL,               -- 用户输入 JSON
  outputs TEXT,                      -- 各节点 output_key → 内容 JSON
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 3.2 配置 DSL（JSON）

结构见 interview 阶段设计稿，要点：

- `nodes[]`：`id` / `type`（llm | tool | human）/ `output_key`
  - `llm` 节点：`agent.system_prompt` 必填，`kb_ids` / `tools` / `model_id` 可选（节点级覆盖）
  - `tool` 节点：`tool`（REGISTRY 内名字）+ `args`（支持 `${output_key}` 插值）
  - `human` 节点：`prompt`（展示给审批人）、可选 `timeout_hours`（首期仅记录不强制）
- `edges[]`：`from` / `to` / 可选 `when`（首期仅支持人审决策值比较：`approved` / `rejected`）
- `limits.max_revisions`：条件循环上限，超限自动终止为 failed（防死循环）

### 3.3 运行时（flow_runner）

- 发起时按 definition 动态 build `StateGraph`：每个节点一个函数，`human` 节点用 `interrupt()`（复用 langgraph HITL）
- `thread_id = flow:{run_id}`，与聊天会话同用 `AsyncSqliteSaver` checkpointer → 人审暂停可跨进程恢复
- `llm` 节点复用 `get_agent_for(system_prompt, agent_id, model_id)` 缓存构建（含 KB/MCP 装配）
- 节点产出写入共享 state（`output_key` 字典），同时落 `flow_runs.outputs`
- 循环守卫：同一条件边连续通过次数超过 `max_revisions` → failed

### 3.4 API（Admin 管理流程；登录用户发起/审批）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/flows` | 列表 / 创建（definition JSON 校验后入库） |
| GET/PUT/DELETE | `/api/flows/{id}` | 详情 / 更新（bump version）/ 删除 |
| POST | `/api/flows/{id}/runs` | 发起流程实例（body: 用户输入） |
| GET | `/api/flow-runs?flow_id=` | 实例列表（状态/当前节点） |
| GET | `/api/flow-runs/{run_id}` | 实例详情（含 outputs、待审批内容） |
| POST | `/api/flow-runs/{run_id}/resume` | 人审决策（复用聊天 resume 协议：decisions[]） |
| POST | `/api/flow-runs/{run_id}/cancel` | 取消 |
| GET(SSE) | `/api/flow-runs/{run_id}/stream` | 进度事件流（复用聊天 SSE 协议 + 新增 `flow_step` 事件：`{node, status}`） |

### 3.5 前端（最小可用）

- 后台管理新增「流程」页：列表 + 详情（JSON 文本域编辑，前端做 JSON 合法性校验）+ 发起入口
- 「流程运行」页：发起（选流程 + 填输入）→ 进度展示（节点时间线，SSE）→ 人审时复用 hitl-panel 样式展示 prompt 与 批准/拒绝(+意见) 按钮
- 左侧导航入口追加（顶栏 nav 不动）

## 4. 设计决策

- **选 StateGraph DSL 而非 deepagents subagents 配置化**：诉求是确定性步骤 + 人审门；subagents 是 LLM 自主委派，不保证步骤顺序与人审时机（记录于 intent）
- **人审复用 langgraph interrupt + 现有 resume 协议**：前端 hitl-panel 与后端 Command(resume=...) 全部复用，不新造状态机
- **flow_runs 冗余存 outputs**：列表页不读 checkpointer，避免大 state 反序列化开销
- **JSON 编辑而非画布**：首期最小可用；DSL 字段保持扁平，后续画布只是编辑器升级，配置格式不变

## 5. 测试与验收

- 单测（TDD）：DSL 校验（缺 entry/未知节点类型/边引用不存在节点 → 400）、runner 顺序执行、human 节点 interrupt → resume 继续、condition 边路由、max_revisions 守卫、`${output_key}` 插值、tool 节点调用
- 验收（手动）：配置一条「生成 → 人审 → 修订 → 写文件」示例流程，发起后 SSE 看到逐节点 flow_step，人审点暂停（重启后端后仍可 resume），审批后跑完产出文件
- 性能红线：节点 LLM 调用一律 `asyncio.to_thread`/异步客户端，不得阻塞事件循环（memory 模块教训）

## 6. 里程碑

1. **M1 后端内核**：DSL 校验 + runner（线性 + 人审 + 条件边）+ API（TDD）
2. **M2 前端**：流程管理页 + 运行页 + SSE 进度 + 人审交互
3. **M3 真实场景落地**：用户提供首个业务流程，配置调优并验收
