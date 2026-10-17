# SPEC：记忆模块（DeepAgent Memory）

- intent: `docs/intent/memory-module.md`（2026-10-17 interview-me 确认）
- 蓝本：RAGFlow Memory 模块（四分类记忆 + 检索注入 + 遗忘管理）；第一期裁剪为 Semantic 单类
- 状态：**已交付（2026-10-17）**，实施记录与冒烟结论见 `tasks/memory-module/todo.md` 交付记录一节

## 目标

让 DeepAgent 跨会话记住用户：对话后自动抽取记忆，对话前检索注入，管理页可治理。

## 架构

```
对话流（backend/main.py chat SSE）：
  收到消息 ──► memory.search(user_id, message) top-5 ──► SystemMessage 前插注入
  本轮 done ─► asyncio.create_task(memory.extract(user_id, thread_id, user_text, assistant_text))
                 └─► chat LLM 抽取 JSON 陈述句 ─► 逐条入库（SQLite + Qdrant）

存储：
  SQLite memories 表（复用 agent 库 DB_PATH）
    id TEXT PK | user_id TEXT | content TEXT | memory_type TEXT DEFAULT 'semantic'
    enabled INTEGER DEFAULT 1 | source_thread TEXT | created_at TEXT
  Qdrant collection `memories`（与知识库隔离，dense-only，复用 kb.settings 的 embedding 配置）
    payload: {memory_id, user_id, content, enabled}
```

## 能力

### M1 记忆存储（memory/store.py）

- `init_memories_table()`：建表（main.py lifespan 调用）
- `add_memory(user_id, content, source_thread, memory_type='semantic') -> dict`：入库返回条目
- `list_memories(user_id=None, enabled=None) -> list`：管理列表（user_id/enabled 可选过滤）
- `set_enabled(id, enabled)`：软停用（注入与检索跳过 disabled）
- `forget_memory(id)`：硬删除（同时删 Qdrant 点）

### M2 向量检索（memory/vector.py）

- `ensure_collection()`：Qdrant collection `memories`（维度取 kb embedding 当前配置）
- `upsert_memory(entry)`：embedding 后写入点
- `search(user_id, query, top_k=5) -> list[entry]`：向量检索，filter user_id + enabled=true；embedding 不可用时返回空列表（静默降级，不影响对话）
- `delete_points(memory_id)`：遗忘时同步删点

### M3 自动抽取（memory/extract.py）

- `extract_and_save(user_id, thread_id, user_text, assistant_text)`：
  - chat LLM = agent/model_store.get_default()，无则回退环境变量（MODEL_NAME / OPENAI_API_KEY / OPENAI_BASE_URL，与 deep_agent 同链；冒烟期发现本部署 model_configs 为空，纯查 model_store 会静默跳过）
  - prompt 要求输出 JSON 数组：0-3 条第三人称陈述句（"用户偏好 X"），无值得记的输出 `[]`
  - 解析失败 / LLM 异常：静默返回（后台任务不能炸）
  - 入库走 store + vector
- main.py 在本轮 SSE `done` 后 `asyncio.create_task` 调用

### M4 对话注入（main.py chat 流）

- 进入 agent 前调 `vector.search(user_id, 消息文本, top_k=5)`
- 有结果则在 input messages 最前插 `SystemMessage(content="以下是关于该用户的已知记忆（供参考，勿主动罗列）：\n- ...")`
- 检索异常按无记忆处理

### M5 管理 API（memory/api.py，挂 require_admin）

| 端点 | 说明 |
|---|---|
| `GET /api/memory?user_id=&enabled=` | 条目列表 |
| `POST /api/memory` `{content}` | 管理员手动添加（user_id=admin 本人） |
| `PUT /api/memory/{id}/enabled` `{enabled}` | 启停 |
| `DELETE /api/memory/{id}` | 遗忘（SQLite + Qdrant） |

### M6 前端管理页（MemoryView.vue）

- 路由 `/admin/memory`，侧边栏「智能体」组加「记忆」入口
- 列表卡片：内容、创建时间、来源 thread、启停开关、删除按钮；用户过滤下拉
- api 层 `frontend/src/api/memory.js`

## 非目标（二期）

- Episodic / Procedural / Raw 分类、Agent 级记忆、团队共享
- 容量上限与自动遗忘策略（RAGFlow 5MB + LRU 式遗忘）
- 聊天页显式展示记忆
- embedding 配置变更后的记忆重建（维度不匹配时需手动清空 memories collection，与知识库同策略）

## 验收

- TDD：store CRUD / extract（mock LLM，成功与静默失败）/ vector（mock embed，检索与降级）/ api 契约 / 注入（input 含 SystemMessage 记忆）
- 对话两轮：第一轮说"记住我喜欢简洁回答"，第二轮新 thread 问"我喜欢什么风格"，回答体现记忆
- 管理页：抽取条目可见、启停后新对话不再体现、删除生效
- 全量 pytest 通过 + npm build + 浏览器冒烟
