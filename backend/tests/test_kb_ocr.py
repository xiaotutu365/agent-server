"""kb/ocr.py 按页混合提取单测：渲染/OCR 通过 monkeypatch 接缝隔离，不依赖真实引擎。"""

import os
import tempfile

import pytest
from pypdf import PdfWriter

from kb import ocr


def _blank_pdf(pages: int) -> str:
    """生成 pages 页空白 PDF（无文本层），仅提供页数；页内容由测试桩决定。"""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_mixed_pdf_page_routing(monkeypatch):
    """文本层达标页直接用且不触发 OCR；不达标页走 OCR 并按 (y,x) 阅读序拼接；空页计入 empty_pages。"""
    path = _blank_pdf(3)
    try:
        long_text = "文本层内容。" * 50  # 350 字符 ≥ 150 阈值
        counter = {"i": 0}

        def fake_page_text(page):
            i = counter["i"]
            counter["i"] += 1
            return long_text if i == 0 else ""

        ocr_calls = []

        def fake_ocr_page(p, idx):
            ocr_calls.append(idx)
            if idx == 1:
                # 乱序块：断言按 (y, x) 排序后为 A(10,200) → C(50,5) → B(50,10)
                return [(50.0, 10.0, "第二页B"), (10.0, 200.0, "第二页A"), (50.0, 5.0, "第二页C")]
            return []  # 第 3 页纯装饰页

        monkeypatch.setattr(ocr, "_page_text", fake_page_text)
        monkeypatch.setattr(ocr, "_ocr_page", fake_ocr_page)

        text, stats = ocr.extract_pdf_text(path)
        assert ocr_calls == [1, 2], "文本层达标页不应触发 OCR"
        assert text == long_text + "\n第二页A\n第二页C\n第二页B"
        assert stats == {"pages": 3, "text_pages": 1, "ocr_pages": 1, "empty_pages": 1}
    finally:
        os.remove(path)


def test_progress_cb_per_page(monkeypatch):
    """每完成一页回调 progress_cb(done, total)。"""
    path = _blank_pdf(2)
    try:
        monkeypatch.setattr(ocr, "_page_text", lambda page: "")
        monkeypatch.setattr(
            ocr, "_ocr_page", lambda p, i: [(0.0, 0.0, "识别内容。" * 50)]
        )
        seen = []
        ocr.extract_pdf_text(path, progress_cb=lambda d, t: seen.append((d, t)))
        assert seen == [(1, 2), (2, 2)]
    finally:
        os.remove(path)


def test_all_empty_raises_low_quality():
    """整份 OCR 兜底后仍无字 → 抛 LowQualityExtraction（conftest 的 autouse 桩使所有页 OCR 为空）。"""
    path = _blank_pdf(16)
    try:
        with pytest.raises(ocr.LowQualityExtraction):
            ocr.extract_pdf_text(path)
    finally:
        os.remove(path)


def test_sparse_document_accepted_after_ocr(monkeypatch):
    """新语义钉住：闸门只看整份是否仍无字，不再按每页阈值否决（旧公式会误拒 8 空页文档）。"""
    path = _blank_pdf(16)
    try:
        monkeypatch.setattr(ocr, "_page_text", lambda page: "")
        monkeypatch.setattr(
            ocr,
            "_ocr_page",
            lambda p, i: [(0.0, 0.0, "内容" * 70)] if i % 2 == 0 else [],
        )
        text, stats = ocr.extract_pdf_text(path)
        assert stats["ocr_pages"] == 8 and stats["empty_pages"] == 8
        assert len(text.strip()) >= ocr.MIN_PDF_CHARS_PER_PAGE
    finally:
        os.remove(path)


def test_check_pdf_quality_document_floor():
    """整份字符数低于文档下限报错，等于放行；零页文档一律拒绝。"""
    with pytest.raises(ocr.LowQualityExtraction):
        ocr.check_pdf_quality("x" * (ocr.MIN_PDF_CHARS_PER_PAGE - 1), 16)
    ocr.check_pdf_quality("x" * ocr.MIN_PDF_CHARS_PER_PAGE, 16)
    with pytest.raises(ocr.LowQualityExtraction):
        ocr.check_pdf_quality("x" * 1000, 0)


@pytest.mark.ocr
def test_real_ocr_chinese_page(tmp_path):
    """慢集成（默认由 pytest.ini addopts 排除，`pytest -m ocr` 单跑）：PyMuPDF 渲染中文 → RapidOCR 真识别。"""
    import pymupdf

    path = str(tmp_path / "ocr_sample.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (72, 120), "中央处理器 CPU 由运算器和控制器组成", fontname="china-s", fontsize=24
    )
    doc.save(path)
    doc.close()

    blocks = ocr.ocr_page(path, 0)  # 直调真实现，绕过 autouse 桩接缝
    # OCR 对西文字符间距不稳定（如 "C PU"），按去空白归一化后断言关键字
    compact = "".join("".join(b[2] for b in blocks).split())
    assert "CPU" in compact, f"OCR 结果应含 CPU，实际：{compact!r}"
    assert "运算器" in compact, f"OCR 结果应含 运算器，实际：{compact!r}"
