# 实施计划：kb-ocr-ingest（图片型 PDF OCR 入库 + 入库异步化）

> Spec：[docs/specs/SPEC-kb-ocr-ingest.md](../../docs/specs/SPEC-kb-ocr-ingest.md)（2026-10-21 评审通过）
> 选型：[ADR-003](../../docs/adr/ADR-003-local-ocr-pipeline.md)　意图：[kb-ocr-ingest.md](../../docs/intent/kb-ocr-ingest.md)

## 策略

- 垂直切片：每个任务交付一条可验证路径，不按 DB/API/UI 水平分层。
- TDD：先写失败测试再实现；OCR 真实引擎用 `@pytest.mark.ocr` 隔离（默认跳过，验收时单跑一次）。
- 契约变更（同步→202）在 Phase 2 Checkpoint 需人工确认后才动前端。
- 测试解释器：`backend\venv\Scripts\python.exe -m pytest`（在 backend 目录）。

## 阶段与任务

| Phase | 任务 | 尺寸 | 依赖 |
|---|---|---|---|
| 1 | T1 按页混合提取 `kb/ocr.py`（mock OCR） | M | — |
| 1 | T2 引入 rapidocr-onnxruntime/pymupdf + 慢集成测试 | S | T1 |
| — | ✅ Checkpoint 1：全量 pytest 绿；`-m ocr` 单跑通过一次 | | |
| 2 | T3 `kb/tasks.py` 任务表 + inline runner + startup 清理 | M | T1 |
| 2 | T4 api.py 202 契约 + 任务查询端点 + 闸门测试语义适配 | M | T2,T3 |
| — | ✅ Checkpoint 2：后端契约全绿；**人工确认接口变更后进入前端** | | |
| 3 | T5 前端轮询（api/kb.js + KnowledgeBase.vue） | M | T4 |
| — | ✅ Checkpoint 3：浏览器上传文本型 PDF 走查全流程 | | |
| 4 | T6 端到端验收：重启后端 + 重入库《1.计算机硬件.pdf》+ 检索命中 | S | T5 |

## 风险

- onnxruntime/pymupdf 在 Windows 安装体积与首次模型加载耗时——T2 提前暴露。
- ~~进程池 worker 撞 Qdrant local 文件锁~~ 已在 spec C2 定案：worker 只做提取/切分/embed，upsert 与旧片段删除留在主进程。
- 前端轮询与既有"上传中"文案改造范围蔓延——只做 spec C3 列的三点。
