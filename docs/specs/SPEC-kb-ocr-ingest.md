# SPEC: kb-ocr-ingest（图片型 PDF OCR 入库 + 入库异步化）

> 意图来源：[docs/intent/kb-ocr-ingest.md](../intent/kb-ocr-ingest.md)（interview-me，2026-10-21 已确认，六项决策逐项通过）
> 需求追溯：[bugs/pdf-low-quality-extraction](../../bugs/pdf-low-quality-extraction/fix.md)（质量闸门遗留"如需 OCR 另立需求"）；[docs/intent/kb-reingest-and-fallback.md](../intent/kb-reingest-and-fallback.md) 曾将扫描件 OCR 列为 out of scope，本 spec 承接
> 选型记录：[ADR-003-local-ocr-pipeline](../adr/ADR-003-local-ocr-pipeline.md)（OCR 引擎 / 页渲染 / 执行模型，含否决方案）
> 契约影响：变更 [SPEC-knowledge-base](SPEC-knowledge-base.md) L2 的上传/重入库接口（同步 → 202 异步）

## 背景

质量闸门（2026-10-21）拦截了图片型 PDF 静默入库，但课件类资料（如《1.计算机硬件.pdf》，16 页中文全部绘制在图片/矢量层）确实需要入库检索。OCR 后单文档耗时可达分钟级，现有同步上传接口无法承载，故入库全面异步化。

## 能力 C1：按页混合提取（`backend/kb/ocr.py`，新）

- `extract_pdf_text(path, progress_cb=None) -> (text, stats)`
  - 逐页判定：pypdf 该页 `extract_text()` 字符数 ≥ `MIN_PDF_CHARS_PER_PAGE`（150，沿用闸门常量）→ 直接用文本层；否则 PyMuPDF 渲染该页（zoom=2.0）→ RapidOCR 识别 → 文本块按 (y, x) 阅读序拼接。
  - **文本层提取保持 pypdf 不换引擎**：与既有入库行为一致，PyMuPDF 只承担渲染（最小化对文本型 PDF 的回归面）。
  - OCR 后仍为空的页（纯装饰页）跳过，计入 `stats.empty_pages`。
  - `progress_cb(done_pages, total_pages)`：每完成一页回调（任务进度来源）。
  - `stats = {pages, text_pages, ocr_pages, empty_pages}`，随任务落库便于排查。
- 整份提取后总字符仍低于阈值 → 抛 `LowQualityExtraction`（异常类型保留，**语义变更**：从"图片型拒绝"变为"OCR 兜底后整份仍无字"）。
- 依赖：新增 `rapidocr-onnxruntime`、`pymupdf`（ADR-003）。RapidOCR 实例进程级惰性单例（模型加载 ~秒级，勿每页重建）。
- 非 PDF 路径不变（`_load_text` 的 txt/md/docx 分支）。

## 能力 C2：入库任务机制（`backend/kb/tasks.py`，新）

### 数据模型

`kb_ingest_tasks` 表，与 `agent.model_store.DB_PATH` 同库（`CREATE TABLE IF NOT EXISTS` 幂等初始化）：

| 字段 | 说明 |
|---|---|
| id | uuid PK |
| kb_id / source | 目标库与展示文件名 |
| kind | `upload` \| `reingest` |
| status | `queued` \| `running` \| `done` \| `failed` |
| total_pages / done_pages | 进度（非 PDF 恒 0/0） |
| chunks | 终态时写入片段数 |
| error | 失败原因（可读中文） |
| created_at / updated_at | ISO 时间 |

### 执行模型

- ProcessPoolExecutor（max_workers=1，串行队列——上传是低频管理操作）。
- **进程边界（关键约束）**：Qdrant local 嵌入式模式为单进程文件锁，worker 进程不得触碰 store。分工：
  - worker（子进程）：`extract_pdf_text`（含 OCR，逐页回调写进度）→ 切分去重 → embed（dense/sparse）→ 返回 points 数据。
  - 主进程（future 回调）：`store.upsert_points` 写入；reingest 的 `delete_document` 也在主进程、且仅在 worker 提取+向量化**成功后**执行（保持"失败不丢数据"）。
  - 任何异常（含 `EmbeddingUnavailable`、`LowQualityExtraction`）→ failed + error 文本，**不写向量库**。
- 进度：worker 每页回调写 `done_pages`（SQLite 跨进程可见）。
- 启动清理：app startup 时把 `queued/running` 残留任务置 `failed("服务重启中断")`，不做断点续跑。
- 测试注入：`RUNNER="inline"` 时同进程直接执行（TestClient 契约测试用，避免跨进程 flaky）。

### 契约（提供方：kb-ocr-ingest；破坏性变更，不留兼容路径）

| 方法 | 路径 | 说明 | 响应 |
|---|---|---|---|
| POST | `/api/kb/{kb_id}/documents` | 上传→留档→建任务 | **202** `{task_id, kb_id, file}` |
| POST | `/api/kb/{kb_id}/documents/reingest` | 重入库→建任务 | **202** `{task_id, kb_id, file}`；无留档仍 404 |
| GET | `/api/kb/ingest-tasks/{task_id}` | 查任务（轮询用） | 任务行全字段 |
| GET | `/api/kb/{kb_id}/ingest-tasks?active=true` | 进行中任务列表 | `{tasks: [...]}` |

- 校验前置在 API 层不变：kb_id 非法 400、超大小 413；`kb_id` 不存在时上传仍隐式建库（沿用现状）。
- 权限沿用 kb router 的 `require_admin`。

## 能力 C3：前端改造（`KnowledgeBase.vue` + `api/kb.js`）

- `uploadDoc/reingestDocument` 返回 `task_id`；新增 `getIngestTask`、`listActiveIngestTasks`。
- 提交后进入轮询（2s 间隔）：状态条展示「排队中 / 处理中 x/y 页 / 完成（n 片段）/ 失败：原因」；完成后刷新文档列表，失败展示可读错误。
- 进入页面时拉 `active=true` 恢复进行中任务的展示（刷新不丢进度视图）。

## 测试

- `test_kb_ocr.py`（单元，monkeypatch OCR 引擎）：混合 PDF 逐页分流（文本页不调 OCR）、空页跳过、progress_cb 逐页触发、整份无字抛 `LowQualityExtraction`。
- `test_kb_ingest_tasks.py`（契约，inline runner）：upload 202→轮询 done→片段可检索；reingest 提取失败→failed 且旧片段保留；startup 清理 running→failed；active 列表。
- 改写 `test_kb_ingest.py` 现有 3 项闸门测试到新语义（拒绝场景仅剩"整份无字"），**不静默删除**。
- 慢集成（`@pytest.mark.ocr`，默认跳过）：PyMuPDF 渲染中文文本图 → RapidOCR 真识别断言。
- 全量 pytest 绿 + `pytest -m ocr` 单独跑通一次作为验收项。

## 验收标准（spec 级）

1. 上传《1.计算机硬件.pdf》：进度可见（x/16 页）→ done → 检索"CPU"相关中文查询命中 OCR 内容。
2. 文本型 PDF/txt/md 入库不触发 OCR（stats.ocr_pages=0），行为与现状一致。
3. 后端重启不留僵尸任务；失败任务零写入向量库。

## 不做（Out of scope）

云端 OCR/视觉大模型、表格结构还原、图片内容理解、存量自动迁移（上线后手动对留档点「重新入库」验证）、任务并发调优与断点续跑、非 PDF 的 OCR。
