import os
import tempfile

from kb import ingest


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
