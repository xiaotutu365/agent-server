# 知识库功能完善 · 任务清单

> spec: [docs/specs/SPEC-knowledge-base.md](../../docs/specs/SPEC-knowledge-base.md) · plan: [plan.md](plan.md)

## Phase 0 · 环境（L1）

- [x] **T1 端到端冒烟**（S）
  - 验收：`pytest backend/tests/test_kb_*.py` 全绿；本地建库→上传→检索 API 冒烟通过
  - 验证：pytest + curl 冒烟脚本
  - 涉及：无代码改动（若有兼容问题记录进 spec/bug）
  - 依赖：无

## Phase 1 · 文档管理（L2）

- [x] **T2 文档列表/删除 API**（M，TDD）
  - 验收：GET/DELETE `/api/kb/{kb_id}/documents` 按 spec 契约工作；删除后检索不命中
  - 验证：新增 `backend/tests/test_kb_documents.py`（先 red 后 green）
  - 涉及：`backend/kb/api.py`、`backend/kb/store.py`
  - 依赖：T1
- [x] **T3 工作区文档列表 UI**（M）
  - 验收：打开库可见文档列表（名称/片段数/删除确认）；上传完成刷新列表
  - 验证：前端 HMR 无报错 + 浏览器冒烟
  - 涉及：`frontend/src/components/KnowledgeBase.vue`、`frontend/src/api/kb.js`
  - 依赖：T2
- **Checkpoint 1**：pytest 全绿；建库→上传→文档列表→删除全流程人工冒烟通过

## Phase 2 · 检索调优（L3）

- [x] **T4 检索结果透出 score + 运行时参数覆盖**（M，TDD）
  - 验收：search 响应含 score（RRF，降序）；top_k/candidate/rrf_k 可选入参覆盖默认
  - 验证：扩展 `test_kb_retrieval.py`（先 red 后 green）
  - 涉及：`backend/kb/retrieval.py`、`backend/kb/api.py`
  - 依赖：T1
- [x] **T5 检索预览 UI**（S）
  - 验收：检索结果卡片显示来源/片段号/分数；改配置后检索立即生效
  - 验证：HMR 无报错 + 浏览器冒烟
  - 涉及：`frontend/src/components/KnowledgeBase.vue`、`frontend/src/api/kb.js`
  - 依赖：T4
- **Checkpoint 2**：调参→检索预览闭环人工确认

## Phase 3 · Agent 挂载与引用（L4）

- [x] **T6 kb_ids 字段 + 工具闭包绑定**（M，TDD）
  - 验收：agent_config 增 kb_ids（迁移向后兼容）；kb 工具按绑定列表过滤（空=全库旧行为）
  - 验证：新增 `test_kb_agent_mount.py`；`test_agent_cache_invalidation.py` 回归仍绿
  - 涉及：`backend/agent/config_store.py`、`backend/kb/tools.py`、`backend/agent/deep_agent.py`
  - 依赖：T1
- [x] **T7 智能体编辑页挂载 UI**（M）
  - 验收：AgentEditView 可勾选库并保存（与 MCP 区同风格）；热重建后聊天按新挂载检索
  - 验证：HMR + 浏览器冒烟（改挂载→聊天行为变化）
  - 涉及：`frontend/src/views/AgentEditView.vue`、`frontend/src/api/`（agents）
  - 依赖：T6
- [x] **T8 引用来源链路**（M）
  - 验收：kb 工具 tool_end 带 citations；AI 回答下方渲染来源标记（文件名+片段号）
  - 验证：`test_kb_agent_mount.py` 扩展 citations 结构 + 浏览器端到端
  - 涉及：`backend/main.py`、`frontend/src/views/ChatView.vue`
  - 依赖：T6
- **Checkpoint 3**：验收问答——问只有文档里才有答案的问题，回答正确带引用

## Phase 4 · 收尾

- [x] **T9 端到端验证 + code review**（M）
  - 验收：spec 验收三条全过；review 问题清零
  - 验证：全量 pytest、前端 build、人工验收脚本
  - 涉及：文档同步（spec 追溯链接）
  - 依赖：T3 T5 T8
  - **验证记录（2026-10-16）**：
    - pytest 58 passed（含新增 `test_extract_kb_citations`）；前端 `vite build` 通过；HMR 无报错
    - 浏览器冒烟 5 项通过：登录 / 聊天页（含知识库建议问题）/ AgentEdit「知识库挂载」区块 / 知识库页 / 控制台零报错
    - review 修复 3 处：MessageBubble typing 指示器 v-else-if 链被 citations 截断（改为独立 v-if）；`restoreThread` 历史消息缺 `citations: []`（HITL 恢复会崩）；`SearchReq` 隐式可选改 `int | None`
    - 验收第 2 条（真实问答带引用）**待用户配置 embedding 服务后人工确认**：DeepSeek 无 `/v1/embeddings`（404），需在知识库设置中配置其他 embedding 服务；代码链路已由 fake-embedding 测试与 citations 提取测试覆盖
