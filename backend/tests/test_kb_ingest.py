import os
import tempfile

import pytest
from qdrant_client import models

import kb.config as cfg
from kb import ingest, store


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
