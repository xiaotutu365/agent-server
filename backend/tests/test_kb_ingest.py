import os
import tempfile

import pytest
from pypdf import PdfWriter

import kb.config as cfg
from kb import ingest, ocr, store


def _blank_pdf(pages: int) -> str:
    """生成 pages 页空白 PDF（无文本层），模拟扫描件/图片型课件。"""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_ingest_file_chunks_and_upserts():
    long_text = "知识库内容示例。" * 500  # 足够切分为多个片段
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(long_text)
    try:
        n = ingest.ingest_file("ingest_test", path)
        assert n > 1, "长文本应被切分为多个片段"
    finally:
        os.remove(path)


def test_ingest_dedup_within_file():
    fd, path = tempfile.mkstemp(suffix=".txt")
    # 完全重复的内容应只保留一份片段
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("重复段落内容。\n" * 3)
    try:
        n = ingest.ingest_file("ingest_dedup", path)
        # 内容相同 -> 切分后去重为一个片段
        assert n == 1
    finally:
        os.remove(path)


def test_ingest_source_uses_original_filename():
    """上传走临时文件，source 必须是用户上传的原始文件名而非 tmpXXX。"""
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("退货政策：7 天无理由退货。")
    try:
        n = ingest.ingest_file("ingest_source", path, source="policy.md")
        assert n == 1
        pts, _ = store.get_client().scroll(cfg.collection_name("ingest_source"), limit=10)
        sources = {p.payload["source"] for p in pts}
        assert sources == {"policy.md"}, f"source 应为原始文件名，实际 {sources}"
    finally:
        os.remove(path)


def test_ingest_pdf_image_only_rejected():
    """图片型/扫描 PDF（文本层近乎为空）不得静默入库，应抛 LowQualityExtraction。"""
    path = _blank_pdf(16)
    try:
        with pytest.raises(ingest.LowQualityExtraction):
            ingest.ingest_file("ingest_lowq", path)
    finally:
        os.remove(path)


def test_check_pdf_quality_threshold_boundary():
    """闸门已迁至 kb/ocr.py 且语义变更（OCR 兜底后整份仍无字才否决）：低于文档下限报错，等于放行。"""
    with pytest.raises(ocr.LowQualityExtraction):
        ocr.check_pdf_quality("x" * (ocr.MIN_PDF_CHARS_PER_PAGE - 1), 16)
    ocr.check_pdf_quality("x" * ocr.MIN_PDF_CHARS_PER_PAGE, 16)

# 注：原 test_reingest_low_quality_keeps_existing_chunks（同步 reingest_document 闸门）
# 已随 API 异步化迁移至 test_kb_ingest_tasks.py::test_reingest_failure_keeps_old_chunks
# 与 ::test_api_reingest_failure_keeps_old_chunks（任务机制覆盖同一保证：失败不丢旧片段）。
