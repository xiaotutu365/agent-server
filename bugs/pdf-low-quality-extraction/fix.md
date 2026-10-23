# 修复记录

## 根因

图片型/扫描 PDF 的中文内容不在文本层（字体 ToUnicode CMap 仅映射 ASCII），pypdf 只能取出碎片；入库管线对提取结果无任何质量校验，碎片被切分、向量化后污染检索。

## 改动范围

- `backend/kb/ingest.py`
  - 新增 `LowQualityExtraction(ValueError)`、`MIN_PDF_CHARS_PER_PAGE = 150`
  - 新增 `_check_pdf_quality(text, pages)`：每页提取字符数低于阈值即拒绝
  - 新增 `_load_text_checked(path)`：PDF 读取后过闸门；`ingest_file` 改用它
  - `reingest_document`：删除旧片段**之前**先过闸门，被拒绝时保留旧片段（不静默丢数据）
- `backend/kb/api.py`：upload / reingest 捕获 `LowQualityExtraction` → HTTP 400 + 可读提示（含"请先 OCR"）
- `backend/tests/test_kb_ingest.py`：3 项回归测试（拒绝入库 / 阈值边界 / reingest 保旧片段）
- `backend/tests/conftest.py`：附带修复测试隔离缺陷（见 `bugs/kb-tests-model-store-leak.md`）

## 回归测试

`tests/test_kb_ingest.py::test_ingest_pdf_image_only_rejected`、
`::test_check_pdf_quality_threshold_boundary`、
`::test_reingest_low_quality_keeps_existing_chunks`（先 red 后 green）

## 验证结果

- 全量 `pytest`：219 passed
- 真实文件端到端：`E:\BaiduNetdiskDownload\1.计算机硬件.pdf` 被闸门拦截，报错文案含页数/字符数与 OCR 指引
- 存量清理：`DELETE /api/kb/eda1/documents?file=1.计算机硬件.pdf` → deleted=3，文档列表已空

## 遗留说明

- 未引入 OCR（用户确认仅做闸门）；如需支持图片型 PDF，另立需求走 DEFINE 流程
- 新代码需重启后端才生效（当前运行进程仍是旧代码）
