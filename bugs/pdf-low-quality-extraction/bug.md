# 图片型 PDF 静默入库产生垃圾切片

## 现象

用户上传 `1.计算机硬件.pdf`（16 页课件）到 eda1 知识库后，检索/分片预览内容"很乱"：切片全是 ASCII 碎片（`CPU ALU AC DR`、`CRC G(x)`、孤立数字），没有任何中文句子。

## 复现步骤

1. 取 `E:\BaiduNetdiskDownload\1.计算机硬件.pdf`
2. `backend\venv\Scripts\python.exe` 下用 pypdf `PdfReader` 逐页 `extract_text()`
3. 16 页共提取 2063 字符（平均 129 字符/页），`has CJK: False`

## 证据

- 每页字符数：`[54,123,142,216,220,14,113,495,78,59,138,85,153,38,75,60]`；page1 有 51 张内嵌图片
- 全文档仅 3 个字体（`/CIDFont+F1/F2/F3`，Type0），ToUnicode CMap 的 bfchar 目标全部落在 ASCII 区（`<0020>–<0079>`），**无任何 CJK 码位**
- 结论：中文内容不在 PDF 文本层（以图片/矢量曲线绘制），任何纯文本提取器（含 PyMuPDF/pdfplumber）都取不出中文，非 pypdf 缺陷

## 根因

`backend/kb/ingest.py` 入库管线对提取结果无质量校验：`_load_text` 返回什么就切什么、embed 什么、upsert 什么。图片型/扫描件 PDF 的碎片文本被静默向量化，污染检索结果。

## 期望行为

- 入库时检测提取质量，图片型 PDF 直接报错（400）提示"需 OCR"，不写入向量库
- `reingest` 路径不得因新校验而先删旧片段再失败（避免静默丢数据）

## 处理决定（用户已确认）

- 方案：仅加质量闸门，不引入 OCR 依赖
- 存量：删除 eda1 中该 PDF 已入库的垃圾切片
