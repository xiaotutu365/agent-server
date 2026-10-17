# SPEC: knowledge-base（知识库）

> 意图来源：[docs/intent/knowledge-base.md](../intent/knowledge-base.md)（interview-me，2026-10-16 已确认）
> 追加意图：[docs/intent/kb-chunking-strategy.md](../intent/kb-chunking-strategy.md)（分片策略，2026-10-17 已确认）、[docs/intent/kb-eval.md](../intent/kb-eval.md)（检索评测，2026-10-17 已确认）、[docs/intent/kb-reingest-and-fallback.md](../intent/kb-reingest-and-fallback.md)（重新入库与兜底，2026-10-17 已确认）、[docs/intent/kb-retrieval-tuning.md](../intent/kb-retrieval-tuning.md)（检索调优，2026-10-17 已确认）
> 选型记录：[docs/adr/ADR-001-langchain-text-splitters.md](../adr/ADR-001-langchain-text-splitters.md)、[docs/adr/ADR-002-ragas-eval.md](../adr/ADR-002-ragas-eval.md)

## 背景

知识库现状：`backend/kb/` 已有雏形——建库/删库/列表（`kb_{kb_id}` 集合）、文档上传（pypdf/docx/text 解析切分，payload: `text/source/kb_id/chunk_idx`）、dense+sparse 混合检索（RRF 融合，`retrieval.py`）、全局配置（`data/kb_settings.json`）、Agent 侧布尔总开关（`config_store.kb_enabled` → `tool_registry.resolve_tools` 过滤 `kb` 工具组）。

三个缺口（见意图声明）：文档是黑盒（传了什么看不见、删不掉单个文档）、检索效果无法验证（score 未透出、调参无预览）、Agent 未真正打通（布尔开关但无库级挂载、回答无引用来源）。

## 能力 L1：环境可用

- Qdrant 支持 local（本地路径，免 Docker）与 remote 两种模式（`kb/config.py` 已实现），本期不做新部署工作，只做**可用性验证**：建库 → 上传 → 检索端到端冒烟。
- 验收：本地 `pytest backend/tests/test_kb_*.py` 全绿；服务启动后前端可建库、上传、检索。

## 能力 L2：文档管理

### 契约（提供方：knowledge-base）

| 方法 | 路径 | 说明 | 响应 |
|---|---|---|---|
| GET | `/api/kb/{kb_id}/documents` | 按 `source` 聚合列出该库文档 | `{"documents": [{"file", "chunks", "size_chars"}]}` |
| DELETE | `/api/kb/{kb_id}/documents` | 删除单个文档（query: `file=<source>`） | `{"deleted": <points 数>}` |

- 实现走 Qdrant scroll（按 payload `source` 过滤聚合）与 delete（filter `source`）。
- 404 语义：库不存在 → 404；文档不存在 → 404。

### 前端（KnowledgeBase.vue 工作区）

- 文档列表区块：名称 / 片段数 / 删除（带确认），沿用列表页视觉规范（`.tbl`）。
- 上传反馈：进行中文案 + 完成后刷新文档列表。

### 测试

`test_kb_documents.py`：聚合列表、按文档删除、删除后检索不再命中。

## 能力 L3：检索调优

### 契约变更

`POST /api/kb/{kb_id}/search`：

- 请求 `SearchReq` 增加可选 `top_k/candidate/rrf_k`（运行时覆盖 `data/kb_settings.json` 默认值，只影响本次检索）。
- 响应 `results[i]` 增加 `score`（RRF 分数）与 `metadata.source/chunk_idx`（已有，spec 明确为必返字段）。

### 前端

- 工作区检索结果卡片：显示来源文件、片段号、分数。
- 配置页（已有调参表单）改动即保存即生效；工作区检索每次按当前配置执行，形成「调参 → 预览」闭环。

### 测试

`test_kb_retrieval.py` 扩展：score 存在且降序、运行时参数覆盖生效。

## 能力 L4：Agent 级挂载与引用来源

### 数据模型（agent-config 增字段）

- `agent_config` 表增加 `kb_ids TEXT NOT NULL DEFAULT '[]'`（挂载的知识库 id 列表）。
- 语义决策（记录"为什么"）：**`kb_ids=[]` 且 `kb_enabled=True` 保持旧行为——检索所有库**；非空则只检索列出的库。理由：不破坏既有 default agent 行为，布尔总开关与库列表正交（总开关管"有没有 kb 能力"，kb_ids 管"检索范围"）。
- `PUT /api/admin/agents/{id}` 已有 `AGENT_CACHE.clear()`（bugs/mcp-agent-cache-stale 修复），新字段随热重建自动生效——验证项：改 kb_ids 后聊天立即按新挂载检索。

### 工具绑定（kb/tools.py + deep_agent）

- `build_agent` 构建时把该 agent 的 `kb_ids` **闭包绑定**进 kb 工具函数（工具运行时按绑定列表过滤，而非全局查所有库）。
- 绑定 `kb_ids=[]` → 行为同旧版（全库检索）。

### 引用来源

- kb 检索工具返回结构化结果（含 `source/chunk_idx/score`）。
- `main.py` SSE `tool_end` 事件：当工具属 `kb` 组时，payload 附 `citations: [{file, kb_id, chunk_idx, score}]`。
- 前端 ChatView：把本轮 AI 回答关联的 kb `tool_end` citations 渲染为消息下方「来源」标记（文件名 + 片段号）。
- 引用原文查看（2026-10-17）：`GET /api/kb/{kb_id}/chunk?source=&chunk_idx=` 按 (source, chunk_idx) 精确取片段（`store.get_chunk`，库/片段不存在 404）；前端引用 badge 可点击，弹模态显示片段正文 + 来源/片段号/RRF 分数，Esc / × / 点遮罩关闭。回答可回溯到原文，替代早期"不做全文预览弹窗"的取舍。

### 前端（AgentEditView.vue）

- 新增「知识库挂载」勾选区（与 MCP 挂载区同风格）：列出所有库，勾选保存进 `kb_ids`。

### 测试

- `test_kb_agent_mount.py`：kb_ids 过滤逻辑（空=全库、非空=仅列出的库）、闭包绑定后工具检索范围正确。
- 回归：`test_agent_cache_invalidation.py` 仍绿（热重建链路未被破坏）。

## 能力 L5：分片策略（全局可配）

> 意图：[docs/intent/kb-chunking-strategy.md](../intent/kb-chunking-strategy.md)。实现选型见 ADR-001：直接用依赖树已有的 `langchain-text-splitters`，不引入 llama-index。

### 数据模型（settings 增字段）

- `kb/settings.py`：`DEFAULTS["chunk_strategy"] = "fixed"`；新增常量 `CHUNK_STRATEGIES = ["fixed", "markdown", "blank_line"]`
- `save_settings` 对 `chunk_strategy` 白名单校验：不在枚举内的值拒绝（HTTP 400）

### 切分行为（kb/ingest.py `_split`）

| 策略 | 切分器 | 行为 |
|---|---|---|
| `fixed`（默认，现行为） | `RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)` | 通用递归切分 |
| `markdown` | `MarkdownHeaderTextSplitter`（#/##/### 标题层级，strip_headers=False） | 按标题节切，保语义完整；单节超 `chunk_size` 再用 Recursive 兜底切 |
| `blank_line` | 按 `\n\n` 正则分段 | 每段一个片段，相邻段不合并（FAQ 分条）；单段超 `chunk_size` 再用 Recursive 兜底切 |

- `chunk_idx` 按新切分顺序编号；payload schema（`text/source/kb_id/chunk_idx`）不变
- 兜底切分保证单片段不超过 embedding 输入上限

### API / 前端

- `GET /api/kb/settings` 返回 `chunk_strategy` 当前值与 `chunk_strategies` 枚举（含各策略一句话说明），供 UI 渲染
- 设置面板新增「分片策略」下拉/单选，保存成功后提示「仅对之后上传的文档生效，已有文档需删除重传」

### 测试

- 三策略切分单元测试：markdown 按标题边界切；blank_line 段间不合并；fixed 与现行为回归一致
- settings 保存非法 `chunk_strategy` → 400
- 上传走 `markdown` / `blank_line` 策略的 ingest（fake embedding），断言片段边界

### 验收（L5）

- 切换策略保存后，新上传文档的片段划分符合所选策略（如 Markdown 按标题、FAQ 按空行）
- 已有文档检索行为不受影响（payload schema 未变）

## 能力 L6：检索评测（Ragas）

> 意图：[docs/intent/kb-eval.md](../intent/kb-eval.md)。选型与评测集双形态设计见 ADR-002。

### 评测集（文件手工维护，无编辑 UI）

- 路径：`backend/data/kb_eval_<kb_id>.json`，条目 `[{"query", "expected_files", "reference"?}]`
- GET `/api/kb/{kb_id}/evalset`：文件不存在时返回示例模板（`"template": true` 标记）；PUT 校验结构（query 非空、expected_files 非空数组）后落盘
- 评测集是**库级**资产，删库不删评测集文件

### 评测运行

- POST `/api/kb/{kb_id}/eval/run` body `{top_k?: int}`（默认取 settings.top_k）
- 每条：`hybrid_search(kb_id, query, top_k)` → 召回片段 `[{text, source, chunk_idx, score, hit}]`（hit = source ∈ expected_files）
- **自算指标**（始终可用）：每条 recall@k = 命中期望文件数/期望文件数；MRR = 首个期望文件排名倒数的均值；汇总 mean
- **Ragas 指标**：仅对有 `reference` 的条目构造 `SingleTurnSample(user_input, retrieved_contexts, reference)`，跑 `context_precision / context_recall`；judge LLM = model_store 默认模型（缺配置/调用失败 → `ragas_available: false` 优雅降级，只返回自算指标）
- 响应：`{items: [...], summary: {recall_at_k, mrr, context_precision?, context_recall?, ragas_available, ragas_error?}}`

### 前端（KbEvalView.vue，2026-10-17 从 KnowledgeBase.vue 模态窗升级为独立页面）

- 独立页面 `/admin/eval`（左侧菜单「知识库 → 检索评测」）：库下拉选择（与路由 query `?kb=` 双向同步，可直达）、评测集 JSON 编辑（textarea，GET 预填/模板提示）、保存、运行（top_k）、汇总指标卡（Recall@k / MRR / Ragas 双轨）+ 逐条明细（问题 + Recall/RR badge + 召回片段卡：来源/排名/片段号/RRF 分数/命中标记/正文）
- 知识库工作区「评测」按钮改为跳转 `/admin/eval?kb=<current>`，KnowledgeBase.vue 中模态窗及评测逻辑已移除

### 测试

- recall@k / MRR 计算单测（命中、部分命中、全 miss）
- evalset 模板返回 / PUT 校验（非法结构 400）
- run 降级路径：judge LLM 不可用 → 只出自算指标（monkeypatch ragas 调用抛异常）
- ragas 指标路径：monkeypatch `evaluate` 返回固定值，断言 summary 透传

### 验收（L6）

- 选库运行评测返回自算指标 + 逐条召回片段；有 reference 且 judge LLM 可用时附 Ragas 指标
- 全流程不因 ragas 缺失/LLM 缺配置而 5xx

## 能力 L7：重新入库与检索兜底（2026-10-17）

intent: `docs/intent/kb-reingest-and-fallback.md`

### 原文件留档（kb/ingest.py）

- 上传成功后原文件复制到 `data/uploads/{kb_id}/{source}`（`archive_file`，basename 清洗防路径穿越，同库同名覆盖，失败不阻断入库），供重新入库取数据源
- 仅留档后上传的文档支持重建；存量旧文档需删除重传一次建立留档

### 重新入库

- `ingest.reingest_document(kb_id, source)`：删旧片段 → 从留档按当前分片策略重建（point id 确定性，同 id 覆盖不累积）
- `POST /api/kb/{kb_id}/documents/reingest?file=`：无留档 404（提示删除重传）；embedding 不可用 400
- 前端文档行「重新入库」按钮：confirm → 调用 → 成功提示 + 刷新列表

### 检索失败兜底（kb/retrieval.py `hybrid_search_ex`）

- dense 侧**任何故障**（未配置 `EmbeddingUnavailable`、网络连接错误等）→ 降级纯 BM25 关键词检索，不 5xx
- 降级原因随每条 metadata.fallback 透出；`hybrid_search_ex` 另返回 (docs, fallback)，**零结果时也携带原因**（BM25 对中文按空白分词，中文语料降级召回有限，空结果更需说明）
- 检索 API 响应顶层 `fallback` 字段；kb 工具输出（LLM 可读）同样透出 `fallback`，AI 会如实告知用户
- 前端检索结果区显示红色降级提示条
- 已知局限：fastembed `Qdrant/bm25` 对中文分词效果差，降级后中文查询可能零召回（机制可用，召回质量受模型限制）

### 测试（tests/test_kb_reingest.py、tests/test_kb_fallback.py）

- 留档存在性、重建片段数一致、重复重建不累积、无留档 404、库不存在 404
- EmbeddingUnavailable 与 ConnectionError 两类故障均降级且带标记；正常路径无标记；search API 零结果也透出 fallback；工具输出带 fallback

## 能力 L8：检索调优——向量权重与相似度阈值（2026-10-17）

> 意图：[docs/intent/kb-retrieval-tuning.md](../intent/kb-retrieval-tuning.md)。参考 RAGFlow Search Settings，仅补检索策略缺失的 2 项；AI summary / related search / mindmap 为搜索应用展示层功能，与聊天内嵌检索不匹配，不做。

### 数据模型（settings 增字段）

- `kb/settings.py`：`DEFAULTS` 新增 `"vector_weight": 0.5`（加权 RRF 中 dense 路权重，sparse 路为 1-w；0.5 等价现行为）与 `"similarity_threshold": 0.0`（0 = 不过滤，现行为）
- `save_settings` 校验：`vector_weight` 必须为 0~1 数值、`similarity_threshold` 必须 ≥ 0，非法拒绝（HTTP 400）

### 检索行为（kb/retrieval.py）

- **加权 RRF**：`_rrf` 支持 per-list 权重——dense 列表贡献 `w/(k+rank+1)`，sparse 列表贡献 `(1-w)/(k+rank+1)`；不采用分数加权融合（dense cosine 与 BM25 分量纲不同，归一化不可靠）
- **阈值过滤**（rerank 之后、截断 top_k 之前）：
  - 配置了 rerank 模型 → `_maybe_rerank` 返回各候选 relevance_score，按 rerank 分过滤
  - 无 rerank → 按 dense cosine 分过滤（Qdrant 返回的 cosine 分需保留映射，不再丢弃）
  - 纯 sparse 召回（无 cosine 分）的片段**保留**——无法判定语义相关性，不误杀
  - dense 降级（embedding 不可用，纯 BM25）→ 整体跳过过滤，保兜底可用性
- 运行时参数覆盖：`hybrid_search` 增可选 `vector_weight / similarity_threshold`，与既有 `top_k/candidate/rrf_k` 同语义（只影响本次检索）

### 前端（KnowledgeBase.vue 设置面板）

- 检索设置区新增两项：向量权重（滑条 0~1，步长 0.05）与相似度阈值（数字输入 ≥0），带提示文案（权重调高偏语义、调低偏关键词精确；阈值调高更严、检索不到预期内容时调低）
- 保存即生效（`PUT /api/kb/settings` 白名单随 DEFAULTS 自动放行），工作区检索按当前配置执行

### 测试

- 加权 RRF：w=1 纯 dense 序、w=0 纯 sparse 序、w=0.5 与现行为一致（回归）
- 阈值：cosine 低于阈值被滤除、纯 sparse 召回片段保留、threshold=0 不过滤（回归）、dense 降级跳过过滤
- settings：非法 vector_weight / 负 threshold → 400
- 运行时覆盖生效

### 验收（L8）

- 默认值下全量检索相关测试回归一致；调高阈值后低相关片段被滤除且工作区可见效果；全局设置保存后对所有库生效

## 验收（整体）

1. `pytest backend/tests/` 全绿。
2. 端到端：建库 → 上传文档 → 文档列表可见 → 在智能体编辑页挂载该库 → 对话问一个**只有该文档才有答案**的问题 → 回答正确且带引用来源（文件名+片段号）。
3. 前端 HMR 无报错，沿用设计系统（无裸 hex、键盘可达）。

## 非目标

OCR/扫描件、网页爬取、文档级权限、多租户共享库（引用全文预览弹窗已于 2026-10-17 实现，见"引用原文查看"）；
分片高级参数数值可调（chunk size/overlap 输入框、自定义分隔符）、每库独立策略、上传时逐次选择、改策略后自动重建全库、语义切分（`SemanticSplitterNodeParser` 类）；
评测：评测集编辑 UI、Ragas TestsetGenerator 自动生成评测集、faithfulness/answer relevancy 等生成层指标、LLM 评分、自动回归、多库横向对比（均列二期）。

## 追溯

- intent: `docs/intent/knowledge-base.md`、`docs/intent/kb-chunking-strategy.md`、`docs/intent/kb-eval.md`、`docs/intent/kb-reingest-and-fallback.md`、`docs/intent/kb-retrieval-tuning.md`
- tasks: `tasks/knowledge-base/`、`tasks/kb-chunking-strategy/`、`tasks/kb-eval/`、`tasks/kb-reingest-and-fallback/`、`tasks/kb-retrieval-tuning/`
- ADR: `docs/adr/ADR-001-langchain-text-splitters.md`、`docs/adr/ADR-002-ragas-eval.md`
