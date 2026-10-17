# 记忆模块（DeepAgent Memory）

意图：docs/intent/memory-module.md | spec：docs/specs/SPEC-memory.md（2026-10-17 已确认，同日交付）

## Phase 1 后端（TDD）

- [x] T1 memory/store.py：memories 表 CRUD + init_memories_table（tests/test_memory_store.py，4 测试）
- [x] T2 memory/vector.py：Qdrant `memories` collection、upsert/search(user_id+enabled 过滤)/delete，embedding 不可用静默返回空（tests/test_memory_vector.py，5 测试）
- [x] T3 memory/extract.py：chat LLM 抽取 JSON 陈述句（0-3 条，[] 合法），解析/LLM 异常静默（tests/test_memory_extract.py，9 测试）
- [x] T4 memory/api.py 四端点（require_admin）+ main.py 接线：lifespan 建表、chat 前检索注入 SystemMessage、done 后 create_task 抽取（tests/test_memory_api.py + tests/test_memory_injection.py）

## Phase 2 前端

- [x] T5 api/memory.js + MemoryView.vue（列表/启停/删除/手动添加/用户过滤）+ 路由 /admin/memory + 侧边栏「智能体 → 记忆」入口

## Phase 3 验证与收尾

- [x] T6 pytest 全量（123 passed）+ npm build + 浏览器冒烟 + 提交

## 实现要点（新会话必读）

- DB 复用 agent.deep_agent.DB_PATH；建表风格参照 agent/auth.py 的 init_users_table
- embedding 复用 kb.embed（dense, _ = embed.embed_query(text)）与 kb.settings 配置；Qdrant client 复用 kb.store.get_client()，但 collection 用独立的 `memories`（不带 kb 前缀）
- 抽取的 chat 模型走 agent.model_store.get_default()，用 langchain_openai.ChatOpenAI 构造；后台任务任何异常只 log
- 注入位置：main.py chat 端点构造 agent input messages 时在最前插 SystemMessage；注意 AGENT_CACHE 与 system_prompt 无关，别动缓存键
- 对话回复全文聚合：main.py SSE 已在流里拼 assistant 文本，done 前可用（先读代码确认变量名）

## 交付记录（2026-10-17）

- 冒烟发现抽取静默不生效：model_configs 表为空（本部署 chat 模型走 agent_config/env），`_get_llm` 只查 model_store 导致静默跳过。已修复为与 deep_agent 相同的回退链（model_store 默认 llm → MODEL_NAME/OPENAI_API_KEY/OPENAI_BASE_URL env），补 2 个测试钉住。
- 端到端验证：对话「请记住：我最喜欢的编程语言是 Python」→ 后台抽取入库（来源 mem-smoke-1）→ 新会话提问回答「Python」（注入生效）→ 管理页启停/删除持久化生效，控制台无报错。
