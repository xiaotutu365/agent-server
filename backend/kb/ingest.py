"""文档入库管线：加载 → 切分 → 去重(hash) → 双向量化 → 写入 Qdrant。"""

import argparse
import hashlib
import os
import uuid

import re

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from qdrant_client import models

import kb.config as cfg
import kb.embed as embed
import kb.settings as settings
from kb import store

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SUPPORTED_EXT = (".txt", ".md", ".pdf", ".docx", ".csv", ".jsonl")


def _load_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if ext == ".docx":
        import docx

        document = docx.Document(path)
        return "\n".join(p.text for p in document.paragraphs)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _fallback(text: str, s: dict) -> list:
    """超长片段兜底：按 chunk_size/overlap 再切，保证单片段不超限。"""
    return RecursiveCharacterTextSplitter(
        chunk_size=s["chunk_size"], chunk_overlap=s["chunk_overlap"]
    ).split_text(text)


def _split_markdown(text: str, s: dict) -> list:
    """按 Markdown 标题层级切（#/##/###），保语义完整；超长节兜底再切。"""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    out = []
    for doc in splitter.split_text(text):
        content = doc.page_content.strip()
        if not content:
            continue
        if len(content) > s["chunk_size"]:
            out.extend(_fallback(content, s))
        else:
            out.append(content)
    return out


def _split_blank_line(text: str, s: dict) -> list:
    """按空行分段，相邻段不合并（FAQ 分条）；单段超长兜底再切。"""
    out = []
    for seg in re.split(r"\n\s*\n", text):
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) > s["chunk_size"]:
            out.extend(_fallback(seg, s))
        else:
            out.append(seg)
    return out


def _split(text: str) -> list:
    """按全局配置的分片策略切分（settings.chunk_strategy）。"""
    s = settings.get_settings()
    strategy = s.get("chunk_strategy", "fixed")
    if strategy == "markdown":
        return _split_markdown(text, s)
    if strategy == "blank_line":
        return _split_blank_line(text, s)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s["chunk_size"], chunk_overlap=s["chunk_overlap"]
    )
    return splitter.split_text(text)


def ingest_file(kb_id: str, path: str, source: str | None = None) -> int:
    """读取单个文件，切分去重后入库，返回新增片段数。

    source：payload 里的来源文件名（列表/引用展示用）。上传走临时文件，
    必须传用户上传的原始文件名；缺省回退为临时路径的 basename。
    """
    display_name = source or os.path.basename(path)
    text = _load_text(path)
    chunks = _split(text)

    # 按内容 hash 去重（同一文件内重复片段只保留首次）
    seen = {}
    for idx, ch in enumerate(chunks):
        h = hashlib.sha256(ch.encode("utf-8")).hexdigest()
        if h not in seen:
            seen[h] = (ch, idx)

    unique = list(seen.values())
    if not unique:
        return 0

    texts = [u[0] for u in unique]
    dense, sparse = embed.embed_documents(texts)

    points = []
    for (ch, idx), dvec, svec in zip(unique, dense, sparse):
        h = hashlib.sha256(ch.encode("utf-8").hex().encode("utf-8")).hexdigest()[:16]
        pid = str(uuid.uuid5(
            uuid.NAMESPACE_URL, f"{kb_id}:{display_name}:{idx}:{h}"
        ))
        points.append(models.PointStruct(
            id=pid,
            vector={cfg.DENSE_NAME: dvec, cfg.SPARSE_NAME: svec},
            payload={
                "text": ch,
                "source": display_name,
                "kb_id": kb_id,
                "chunk_idx": idx,
            },
        ))
    store.upsert_points(kb_id, points)
    return len(points)


def main():
    parser = argparse.ArgumentParser(description="知识库文档入库")
    parser.add_argument("--kb_id", required=True)
    parser.add_argument("--path", required=True, help="文件或目录")
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args()

    store.create_kb(args.kb_id)
    files = []
    exts = settings.supported_ext_set()
    if os.path.isdir(args.path):
        for root, _, fs in os.walk(args.path):
            for f in fs:
                if f.lower().endswith(exts):
                    files.append(os.path.join(root, f))
    else:
        files = [args.path]

    total = 0
    for fp in files:
        if os.path.getsize(fp) > cfg.MAX_FILE_BYTES:
            print(f"跳过（超过 10MB）: {fp}")
            continue
        try:
            n = ingest_file(args.kb_id, fp)
            total += n
            print(f"已入库 {fp}: {n} 片段")
        except embed.EmbeddingUnavailable as e:
            print(f"入库中止：{e}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"处理失败 {fp}: {exc}")
    print(f"完成，共入库 {total} 片段。")


if __name__ == "__main__":
    main()
