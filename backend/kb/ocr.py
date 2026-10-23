"""PDF 按页混合提取：文本层达标页直接用 pypdf 结果；不达标页 PyMuPDF 渲染 + RapidOCR 兜底。

选型见 docs/adr/ADR-003-local-ocr-pipeline.md；spec：docs/specs/SPEC-kb-ocr-ingest.md 能力 C1。
"""

MIN_PDF_CHARS_PER_PAGE = 150  # 页级分流阈值（沿用质量闸门常量）
RENDER_ZOOM = 2.0  # 渲染缩放，约 144dpi，OCR 识别率与耗时的折中

_engine = None


class LowQualityExtraction(ValueError):
    """OCR 兜底后整份文档仍无有效文字，拒绝入库。"""


def _get_engine():
    """RapidOCR 进程级惰性单例（模型加载秒级，勿每页重建）。"""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def _page_text(page):
    """单页文本层提取：保持 pypdf，与既有入库行为一致（测试接缝）。"""
    return page.extract_text() or ""


def _ocr_image(png_bytes):
    """识别单页 PNG，返回 [(y, x, text)] 文本块。"""
    result, _elapse = _get_engine()(png_bytes)
    blocks = []
    for box, text, _score in result or []:
        blocks.append((box[0][1], box[0][0], text))
    return blocks


def ocr_page(path, page_idx):
    """渲染指定页（zoom=2.0）并 OCR，返回 [(y, x, text)]。集成测试走真实现。"""
    import pymupdf  # PyMuPDF 2.0 起 fitz 别名已弃用

    doc = pymupdf.open(path)
    try:
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(RENDER_ZOOM, RENDER_ZOOM))
        png = pix.tobytes("png")
    finally:
        doc.close()
    return _ocr_image(png)


# 测试接缝：单测/autouse 桩替换 _ocr_page；集成测试用 monkeypatch 还原为 ocr_page
_ocr_page = ocr_page


def check_pdf_quality(text: str, pages: int):
    """整份提取质量闸门（OCR 兜底后）：总字符仍低于文档下限即判为无有效内容。

    语义变更（SPEC-kb-ocr-ingest C1）：旧版按「每页阈值×页数」否决图片型 PDF，
    现仅否决「整份仍无字」——装饰空页不再拖累有内容的文档。
    """
    n = len(text.strip())
    if pages <= 0 or n < MIN_PDF_CHARS_PER_PAGE:
        raise LowQualityExtraction(
            f"PDF 经 OCR 兜底后仍无有效文字：{pages} 页共提取到 {n} 个字符"
            f"（低于 {MIN_PDF_CHARS_PER_PAGE} 字符文档下限），"
            "该文件可能是纯装饰/无文字图片文档，请检查文件内容。"
        )


def extract_pdf_text(path, progress_cb=None):
    """按页混合提取 PDF 全文。

    返回 (text, stats)；stats = {pages, text_pages, ocr_pages, empty_pages}，随任务落库便于排查。
    progress_cb(done_pages, total_pages) 每完成一页回调。
    整份仍无字抛 LowQualityExtraction。
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    total = len(reader.pages)
    stats = {"pages": total, "text_pages": 0, "ocr_pages": 0, "empty_pages": 0}
    parts = []
    for idx, page in enumerate(reader.pages):
        raw = _page_text(page)
        if len(raw.strip()) >= MIN_PDF_CHARS_PER_PAGE:
            parts.append(raw)
            stats["text_pages"] += 1
        else:
            blocks = _ocr_page(path, idx)
            if blocks:
                blocks.sort(key=lambda b: (b[0], b[1]))
                parts.append("\n".join(b[2] for b in blocks))
                stats["ocr_pages"] += 1
            else:
                stats["empty_pages"] += 1
        if progress_cb:
            progress_cb(idx + 1, total)
    text = "\n".join(parts)
    check_pdf_quality(text, total)
    return text, stats
