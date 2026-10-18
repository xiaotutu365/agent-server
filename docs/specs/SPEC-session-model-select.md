# SPEC：聊天窗口会话级模型选择

> 状态：已评审通过（2026-10-18）
> 需求来源：会话内需求确认（用户原话要点：与主流 agent 产品体验一致、支持随时切换、切换仅影响当前会话后续消息、历史消息保持不变；候选项直接复用模型配置页已有的对话模型条目，不新增独立模型管理入口；未指定模型的新建会话和存量老会话默认使用全局默认对话模型，行为完全向后兼容）

## 背景

聊天窗口当前只能使用全局默认对话模型（`model_store.get_default("llm")`），无法按会话选择其他已配置的对话模型。用户希望在会话内像主流 agent 产品一样自由切换模型。

## 目标 / 非目标

### 目标

1. 聊天窗口顶栏新增「模型」下拉，候选项 = 模型配置页 `type=llm` 的条目，外加一项「默认（跟随全局）」
2. 随时切换，仅影响该会话后续消息；历史消息不变，不强制开新会话
3. 未选过模型的会话（新建 + 存量）使用全局默认对话模型，完全向后兼容
4. 普通（非管理员）用户可用

### 非目标

- 不做模型管理（增删改仍在模型配置页）
- 不给历史消息标注所用模型
- 不改全局默认模型的设置方式

## 现状事实（spec 依据）

- 模型条目存 SQLite `model_configs` 表（`type` = llm/embedding/rerank，`is_default` 每类型唯一），见 `backend/agent/model_store.py`
- `build_agent`（`backend/agent/deep_agent.py`）模型优先级现状：默认 llm 条目 > Agent 配置 `model_name` > 环境变量；模型在 agent 构建时固定
- agent 实例按 system_prompt / agent_id 缓存（`main.py` `AGENT_CACHE`），`AGENT` 为无指定时的全局单例
- 会话 = langgraph checkpoints（`u{user_id}:{thread_id}`），无独立会话元数据表；`GET /api/threads` 从 checkpoints 推导列表
- 模型列表接口 `GET /api/admin/models` 仅管理员可用，且返回含 `api_key`/`base_url`，不适合直接暴露给聊天页
- 前端 `ChatView.vue` 顶栏已有 Agent 下拉；`onAgentChange` 切换 Agent 会强制开新会话（避免上下文混用），切模型不应如此

## 方案

### 后端

1. **会话模型覆盖存储**：新表 `thread_meta(thread_id TEXT PRIMARY KEY, model_id TEXT NOT NULL DEFAULT '', updated_at TEXT)`（存 `agent_sessions.db`），新增 `agent/thread_meta.py` 提供 get/set/delete（async，aiosqlite，模式同 `model_store.py`）
2. **请求参数与优先级**：`ChatRequest` 增加 `model_id: str | None = None`。`chat_stream` 中语义：非空 → 校验存在且 `type=llm` 后写入 `thread_meta`；**空串 `""`** → 前端选「默认（跟随全局）」，清除会话覆盖；**缺省（None）** → 老客户端行为，沿用覆盖不变。模型已被删除/非 llm 时：服务端记 warning、清理该覆盖记录、回退默认，不中断会话。实际使用模型优先级：**会话覆盖 > 全局默认 llm 条目 > Agent 配置 model_name > 环境变量**
3. **模型覆盖传递**：`build_agent` 增加 `model_id` 覆盖参数（传入时用 `get_model(model_id)` 替代 `get_default("llm")`，`extra` 高级参数同样生效）；`get_agent_for` 缓存键扩展为 `{原key}::model:{model_id}`，不同模型不复用实例；`model_id` 为空时沿用现有键与行为
4. **会话列表回显与清理**：`GET /api/threads` 每项增加 `model_id`（查 thread_meta，无记录为空串）；`DELETE /api/threads/{thread_id}` 级联删除 thread_meta 行
5. **聊天页模型列表接口**：新增 `GET /api/models/chat`（仅需登录，非 admin）：返回 `type=llm` 条目的 `{id, name, model, is_default}`，**不暴露 api_key/base_url**
6. **被删模型回退**：会话覆盖的模型条目被删除后，发送时校验不存在则自动回退全局默认（并清理该覆盖记录），不报错
7. **模型配置变更失效缓存**：`PUT/DELETE /api/admin/models/{id}` 时清空 `AGENT_CACHE`（本功能按 `::model:{model_id}` 缓存实例，否则模型配置更新后旧实例一直被复用；沿用「配置变更后必须失效」既有原则，参照 test_agent_cache_invalidation.py）

### 设计决策

- **持久化时机 = 发送消息时**（`chat_stream` 内随消息写入）：不新增独立保存接口；未发送的临时选择仅存前端内存。代价是「切换后未发送就离开」不记忆——可接受的最小实现
- **切换模型不开新会话**：与 Agent 切换不同（需求明确历史保持不变）；langgraph checkpoint 按 thread_id 存续，换模型仅换 LLM 实例，图拓扑（工具/中间件）一致，历史状态可继续使用
- **HITL resume 同样生效**：resume 请求走同一 `chat_stream` 路径，会话覆盖模型对恢复消息同样适用

### 前端

1. `ChatView.vue` 顶栏 Agent 下拉旁新增「模型」下拉（样式复用 `head-agent`）；选项 = 「默认（跟随全局）」（空值）+ `/api/models/chat` 列表
2. 新会话默认「默认」；`switchThread` 按 threads 返回的 `model_id` 回显；切换模型**不**开新会话
3. `streamChat`（`api/chat.js`）请求体增加 `model_id`（空串表示跟随默认，不写入请求体或显式传空均可，以后端契约为准：仅非空才携带）

## 测试与验收

### 后端（pytest，TDD 先行）

- thread_meta：set/get/delete、覆盖不存在模型时回退并清理
- model_id 覆盖链路：`ChatRequest.model_id` 非空时 `build_agent` 收到覆盖（可用桩断言）、缓存键随模型区分
- `GET /api/models/chat`：普通用户可访问（admin 接口不可）、返回字段不含 api_key/base_url
- `GET /api/threads` 返回 `model_id`；`DELETE` 级联清理 thread_meta
- 存量会话（无 thread_meta 记录）行为不变（回归）

### 前端（手动冒烟）

- 切换模型 → 发消息 → 回复由新模型生成（后端日志/回复风格佐证）、历史消息不变
- 切换会话 → 下拉回显该会话已选模型；未选过的会话显示「默认」
- 普通（非管理员）账号可见下拉且有候选项

### 验收标准（整体）

1. 普通用户在聊天窗口可从「对话模型」列表选择模型，切换后下一条消息由新模型回答
2. 切换会话后模型选择正确回显；未选过模型的会话显示「默认」
3. 全量后端测试通过，无回归
