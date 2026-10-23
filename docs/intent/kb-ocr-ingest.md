# 意图声明：图片型 PDF 的 OCR 入库 + 入库异步化

- 确认时间：2026-10-21
- 确认方式：interview-me 对话（用户逐项确认引擎/触发/粒度/交互/范围/存量六项决策）
- 追溯：源于 [bugs/pdf-low-quality-extraction](../../bugs/pdf-low-quality-extraction/fix.md) 的遗留说明；此前 [kb-reingest-and-fallback](kb-reingest-and-fallback.md) 明确将"扫描件 OCR"列为 out of scope，本意图正式承接

## Outcome

1. **OCR 入库**：图片型/扫描 PDF 可正常入库检索。本地 RapidOCR 引擎，数据不出内网、零调用费用。
2. **按页混合**：逐页判定——文本层达标的页直接用；不达标的页渲染成图片走 OCR；按页序拼接。不存在"整份 PDF 被拒"场景（除非 OCR 失败或整份无字）。
3. **入库全面异步化**：上传/重入库统一改为「提交任务 → 后台执行 → 前端轮询状态」，文档列表展示进度（x/y 页）与终态（完成/失败+原因）。txt/md 秒级完成但走同一机制。

## User / Why now

- 用户：知识库管理员（EDA 场景，课件/ datasheet 大量为图片型 PDF）。
- 动机：质量闸门上线后图片型 PDF 只能拒收，但《1.计算机硬件.pdf》这类课件确实需要入库；OCR 耗时分钟级，同步接口必然超时，异步化是 OCR 的前置。

## Success

- 上传《1.计算机硬件.pdf》→ 任务进度可见（如 3/16 页）→ 完成 → 检索"CPU 组成"能命中 OCR 出的中文内容。
- 文本层正常的 PDF 入库不经过 OCR，速度与现在一致。
- 上传大文件不超时；页面刷新后进行中任务可恢复展示。

## Constraint

- 新增依赖（用户已确认方向）：`rapidocr-onnxruntime`（OCR，模型随包离线）、`pymupdf`（页渲染，AGPL——内部系统使用无碍，见 ADR-003）。
- 任务状态存 SQLite（与现有 agent 库同文件），进程池执行（OCR 为 CPU 密集，不阻塞事件循环）；MVP 单 worker 串行。
- 服务重启时进行中任务标记 failed（原因：服务重启中断），不做断点续跑。
- 存量不做自动迁移：功能上线后对留档文档手动点「重新入库」验证。

## Out of scope

- 云端 OCR / 视觉大模型（智谱 GLM-4V 等）。
- 表格结构还原、图片内容理解（仅文字识别）。
- 全库批量重建任务、任务优先级/并发调优。
- 非 PDF 格式（图片文件直接上传、docx 内嵌图）的 OCR。
