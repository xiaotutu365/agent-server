# 修复清单

## 诊断

- [x] 复现：pypdf 提取 `1.计算机硬件.pdf`，16 页仅 2063 字符，`has CJK: False`
- [x] 定位：全文档 3 个 Type0 字体，ToUnicode CMap bfchar 目标全在 ASCII 区，中文不在文本层（图片/矢量绘制）→ 非 pypdf 缺陷，任何文本提取器都取不出
- [x] 最小化：空白多页 PDF 即可复现"静默入库垃圾"路径（`_load_text` 无质量校验）
- [x] 确认调用面：`ingest_file`（上传/CLI）与 `reingest_document`（重入库）共用 `_load_text`

## 修复（TDD）

- [x] red：`tests/test_kb_ingest.py` 新增 3 项失败测试（图片型 PDF 拒绝 / 阈值边界 / reingest 拒绝时保留旧片段）
- [x] 附带修复测试隔离缺陷 `bugs/kb-tests-model-store-leak.md`：conftest 隔离 `model_store.DB_PATH`（用户新配的 dim=1024 嵌入模型泄漏进 kb 测试导致维度冲突）
- [x] green：`ingest.py` 增加 `LowQualityExtraction` / `MIN_PDF_CHARS_PER_PAGE=150` / `_check_pdf_quality` / `_load_text_checked`；`reingest_document` 先校验后删除
- [x] `kb/api.py`：upload 与 reingest 将 `LowQualityExtraction` 透传为 400（原会落 500"入库失败"）
- [x] 全量 pytest：219 passed
- [x] 端到端验证：真实 PDF 触发 `REJECTED: PDF 文本提取质量过低：16 页仅提取到 2076 个字符…请先 OCR`

## 存量清理

- [x] 经 API 删除 eda1 中 `1.计算机硬件.pdf` 的 3 个垃圾切片（documents 列表已空）
- 留档 `backend/data/uploads/eda1/1.计算机硬件.pdf` 保留：即使误点重入库，闸门会拒绝并给出 OCR 提示
