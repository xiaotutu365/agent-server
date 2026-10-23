# 任务清单：kb-ocr-ingest

> 计划见 [plan.md](plan.md)；spec 为唯一事实来源：[SPEC-kb-ocr-ingest.md](../../docs/specs/SPEC-kb-ocr-ingest.md)
> 执行约定：一次一个任务，先红后绿，完成即勾选并记录验证结果于任务下。

## Phase 1：OCR 提取引擎

### T1 `kb/ocr.py` 按页混合提取（M）
- 涉及文件：`backend/kb/ocr.py`（新）、`backend/tests/test_kb_ocr.py`（新）、`backend/kb/ingest.py`（PDF 分支接 extract_pdf_text）
- 验收（≤3）：
  1. 文本层达标页不调 OCR（mock 断言）；不达标页走 OCR 并按 (y,x) 拼接
  2. OCR 空页跳过计入 stats.empty_pages；progress_cb 逐页触发
  3. 整份无字抛 LowQualityExtraction
- 验证：`pytest tests/test_kb_ocr.py`（OCR 引擎 monkeypatch）
- 依赖：无
- 进度记录：✅ 2026-10-21 先红（ImportError）后绿：`test_kb_ocr.py` 5 项通过（分流/阅读序/stats/progress_cb/整份无字/稀疏文档放行）。`kb/ocr.py` 落地 C1；`ingest.py` PDF 分支接 `extract_pdf_text`，旧闸门三件套（常量/异常/检查）迁至 ocr，re-export `LowQualityExtraction` 供 api 异常映射。闸门语义按 spec 改为「OCR 兜底后整份仍无字」（文档下限 150 字符，不再按页数否决，`test_sparse_document_accepted_after_ocr` 钉住）。conftest 增 autouse `stub_ocr`（图片页返回空块）；`test_kb_ingest.py` 边界测试已就地适配新位置（T4 正式改写）。全量 224 passed。

### T2 真实依赖 + 慢集成测试（S）
- 涉及文件：`backend/requirements.txt`、`backend/tests/test_kb_ocr.py`（@pytest.mark.ocr）
- 验收：
  1. `pip install rapidocr-onnxruntime pymupdf` 成功且记录体积/耗时
  2. fitz 渲染中文文本图 → RapidOCR 识别断言含关键字
  3. `pytest -m "not ocr"` 全绿不受影响
- 验证：`pytest -m ocr` 单跑通过一次
- 依赖：T1
- 进度记录：✅ 2026-10-22 `pip install rapidocr-onnxruntime pymupdf` 成功（rapidocr-onnxruntime 1.4.4、pymupdf 2.0；慢速镜像 ~130kB/s，实际下载耗时很长）。新增体积约 253MB（pymupdf 104 + opencv 112 + rapidocr含模型 15.6 + 其余小件；onnxruntime 45.5MB 已由 fastembed 预装）。注意：PyMuPDF 2.0 起 `fitz` 别名弃用 → `ocr.py` 与集成测试统一改 `import pymupdf`。集成测试 `test_real_ocr_chinese_page` 通过（真识别中文；"CPU" 被断成 "C PU"，断言改去空白归一化）。默认全量 224 passed + 1 deselected；`pytest -m ocr` 单独跑通一次。**Checkpoint 1 达成**。

✅ **Checkpoint 1**：全量 pytest 绿 + `-m ocr` 通过一次。

## Phase 2：任务机制与契约

### T3 `kb/tasks.py` 任务表 + runner（M）
- 涉及文件：`backend/kb/tasks.py`（新）、`backend/tests/test_kb_ingest_tasks.py`（新）
- 验收：
  1. 表幂等创建（同 model_store.DB_PATH 库）；状态机 queued→running→done/failed
  2. RUNNER=inline 同进程执行；startup 清理残留 queued/running→failed("服务重启中断")
  3. worker/主进程分工符合 spec C2 进程边界（upsert 与 reingest 删除留在主进程）
- 验证：`pytest tests/test_kb_ingest_tasks.py`
- 依赖：T1
- 进度记录：✅ 2026-10-22 先红（ImportError: kb.tasks）后绿：`test_kb_ingest_tasks.py` 9 项通过（upload done+可检索、PDF progress 3/3+stats.ocr_pages、LowQuality→failed 零写入、reingest 失败旧片段保留、reingest 成功替换、cleanup_interrupted、list_active、worker 不触碰 store、建表幂等）。`kb/tasks.py` 落地 C2：表含 stats 列（JSON，spec 表格未列但 C1/T6 验收要求）；RUNNER 模块属性（inline 同步执行/process 走 ProcessPoolExecutor(max_workers=1) 惰性单例+done 回调）；DB_PATH 运行时读 model_store（配合 conftest 隔离）。`ingest.py` 抽出 `prepare_points(kb_id,path,source,progress_cb)->(points,stats)`（不触碰 store），`ingest_file` 改为 prepare_points+upsert。PointStruct pickle 往返验证通过（process 模式跨进程返回 points 的前提）。全量 233 passed + 1 deselected。

### T4 API 202 契约 + 闸门测试适配（M）
- 涉及文件：`backend/kb/api.py`、`backend/main.py`（startup 钩子）、`backend/tests/test_kb_ingest_tasks.py`、`backend/tests/test_kb_ingest.py`、`backend/tests/test_kb_reingest.py`
- 验收：
  1. upload/reingest 返回 202 {task_id}；GET task 与 ?active=true 端点可用
  2. 契约测试：202→轮询 done→片段可检索；reingest 提取失败→failed 且旧片段保留
  3. 既有 3 项闸门测试改写至新语义（不静默删除）；全量绿
- 验证：`pytest tests/test_kb_ingest_tasks.py tests/test_kb_ingest.py tests/test_kb_reingest.py` + 全量
- 依赖：T2、T3
- 进度记录：✅ 2026-10-22 先红（7 项 API 契约测试失败：200≠202、GET task 404）后绿：`api.py` upload/reingest 改 202 `{task_id,kb_id,file}`（upload：写临时→隐式建库→留档→任务落点优先留档路径[worker 异步读取，临时文件才可安全删除；留档失败退回临时文件并保留]；LowQuality/Embedding 异常映射移除，改由任务 error 承载）；新增 `GET /api/kb/ingest-tasks/{task_id}`（404 可读中文）与 `GET /api/kb/{kb_id}/ingest-tasks?active=true`（active=false 走 list_tasks 全量）；`main.py` lifespan 接 `cleanup_interrupted()`。删除死代码 `ingest.reingest_document`（同步重入库路径被任务机制取代）。`test_kb_reingest.py` 5 项全改 202+查任务；`test_kb_ingest.py` 重入库闸门测试**迁移**（非静默删除，文件内留注释指向 `test_kb_ingest_tasks.py` 两处等价覆盖）。目标 3 文件 24 passed；全量 237 passed + 1 deselected。

✅ **Checkpoint 2**：后端契约全绿；**人工确认接口变更后才进入 Phase 3**。

## Phase 3：前端

### T5 上传轮询改造（M）
- 涉及文件：`frontend/src/api/kb.js`、`frontend/src/views/KnowledgeBase.vue`（路径以实际为准）
- 验收：
  1. 提交后轮询 2s：展示「排队中/处理中 x/y 页/完成 n 片段/失败：原因」
  2. 完成后刷新文档列表；进入页面恢复 active 任务展示
- 验证：浏览器手动上传文本型 PDF 走查 + 构造失败场景
- 依赖：T4
- 进度记录：✅ 2026-10-22 `api/kb.js`：uploadDoc/reingestDocument 注释更新为 202 契约，新增 `getIngestTask`、`listActiveIngestTasks`。`KnowledgeBase.vue`：新增「入库任务」面板（排队中 / 处理中 x/y 页 / 完成（n 片段）/ 失败：原因 + 隐藏按钮）；提交后 2s 轮询、全部终态自动刷新文档列表与 KB 列表；进入工作区拉 active=true 恢复进行中任务；`busyReingest` 按任务态禁用重入库按钮（替换原 reingesting ref）；离开/卸载停轮询。`npm run build` 通过。浏览器实测（后端新版 :8000 + vite :5175，Checkpoint 2 后经用户授权由我重启后端）：① md 上传→任务面板「完成（1 片段）」→文档列表自动刷新 ✅；② 120 页空白 PDF（API 触发真实 OCR）：面板「处理中 56/120→89/120」增长 ✅、F5 刷新后恢复展示且继续增长（104→106）✅；③ 失败态：任务 failed 120/120、向量库零写入、error 为中文闸门文案（API 层验证；UI 失败行渲染机制经 stream-error 场景证实可用）。注：browser 子代理无法上传真实本地文件（会传截断占位文件），OCR 失败文案截图未走 UI，以 API 断言 + 失败行渲染等价路径覆盖。**Checkpoint 3 达成**。走查数据已清理（t5-walk 库/任务行/留档/临时文件）。

✅ **Checkpoint 3**：浏览器全流程走查通过。

## Phase 4：端到端验收

### T6 真实课件验收（S，需人工参与）
- 步骤：重启后端 → 对留档《1.计算机硬件.pdf》点「重新入库」→ 观察进度 → 检索"CPU 组成"命中 OCR 内容
- 验收：
  1. 任务 done，stats.ocr_pages>0
  2. 中文检索命中，片段内容连贯（非碎片）
- 依赖：T5
- 进度记录：✅ 2026-10-22 真实课件《1.计算机硬件.pdf》（eda1 库，16 页）端到端通过。首轮失败暴露环境数据问题：eda1 旧集合以 1536 维嵌入模型创建，当前配置为 1024 维 → upsert 报 `Vector dimension error`（任务 failed、向量库零写入，恰验证失败路径；OCR 提取 16/16 页本身成功）。删除空集合重建同名库（留档 PDF 不受影响）后重触发：任务 done，耗时约 80 秒，chunks=13，stats={pages:16, text_pages:4, ocr_pages:12, empty_pages:0}（**ocr_pages>0 ✅**）；检索「CPU 组成」命中 chunk_idx=1「CPU的组成：CPU主要由运算器、控制器、寄存器组和内部总线等部件组成…」**内容连贯非碎片 ✅**（含少量课件水印 OCR 噪声「文老师软考教育」等，属图片型课件正常残留）。UI 侧用户实测：进度面板推进、失败文案展示、隐藏按钮均正常。**T1–T6 全部完成，kb-ocr-ingest 特性验收通过。**
