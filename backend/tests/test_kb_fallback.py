"""检索失败兜底：embedding 不可用时混合检索降级为纯 BM25，并在结果中标记。

契约：
- embed_query 抛 EmbeddingUnavailable → hybrid_search 不抛错，仅用稀疏（BM25）检索
- 降级结果的每条 metadata 带 fallback 原因；正常路径不带该标记
- kb 工具输出（LLM 可读 JSON）透出顶层 fallback 字段
"""

import pytest
from qdrant_client import models

import kb.config as cfg
import kb.embed as embed
from kb import store, retrieval

KB = "t_fallback"


@pytest.fixture()
def kb():
    store.drop_kb(KB)
    store.create_kb(KB)
    dim = 4
    texts = ["七天无理由退货。", "整机保修一年。"]
    dense, sparse = embed.embed_documents(texts)
    import uuid

    from qdrant_client import models as m

    points = [
        m.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{KB}:{i}")),
            vector={cfg.DENSE_NAME: d, cfg.SPARSE_NAME: s},
            payload={"text": t, "source": "p.md", "kb_id": KB, "chunk_idx": i},
        )
        for i, (t, d, s) in enumerate(zip(texts, dense, sparse))
    ]
    store.upsert_points(KB, points)
    yield KB
    store.drop_kb(KB)


def test_hybrid_search_falls_back_to_bm25(monkeypatch, kb):
    def unavailable(_text):
        raise embed.EmbeddingUnavailable("未配置 embedding 模型")

    monkeypatch.setattr(embed, "embed_query", unavailable)
    monkeypatch.setattr(
        embed, "sparse_query",
        lambda t: models.SparseVector(indices=[1, 2], values=[0.5, 0.5]),
    )
    docs = retrieval.hybrid_search(kb, "保修")
    assert docs, "降级后仍应返回 BM25 结果"
    assert all(d.metadata.get("fallback") for d in docs)


def test_no_fallback_marker_on_normal_path(kb):
    docs = retrieval.hybrid_search(kb, "保修")
    assert docs
    assert all("fallback" not in d.metadata for d in docs)


def test_hybrid_search_falls_back_on_any_dense_failure(monkeypatch, kb):
    """dense 侧任何故障（含网络连接错误，不只是 EmbeddingUnavailable）都降级 BM25。"""
    def conn_error(_text):
        raise ConnectionError("Connection error.")

    monkeypatch.setattr(embed, "embed_query", conn_error)
    monkeypatch.setattr(
        embed, "sparse_query",
        lambda t: models.SparseVector(indices=[1, 2], values=[0.5, 0.5]),
    )
    docs = retrieval.hybrid_search(kb, "保修")
    assert docs
    assert all(d.metadata.get("fallback") for d in docs)


def test_search_api_exposes_fallback_even_empty(monkeypatch, kb):
    """零结果时 API 仍透出降级原因（BM25 对中文分词有限，空结果更需要说明）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kb.api import router

    def conn_error(_text):
        raise ConnectionError("Connection error.")

    monkeypatch.setattr(embed, "embed_query", conn_error)
    monkeypatch.setattr(
        embed, "sparse_query",
        lambda t: models.SparseVector(indices=[999], values=[0.5]),  # 命中不了的假词
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post(f"/api/kb/{kb}/search", json={"query": "不存在的词"})
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []
    assert data["fallback"]


def test_kb_tool_output_exposes_fallback(monkeypatch, kb):
    from kb import tools

    def unavailable(_text):
        raise embed.EmbeddingUnavailable("未配置 embedding 模型")

    monkeypatch.setattr(embed, "embed_query", unavailable)
    monkeypatch.setattr(
        embed, "sparse_query",
        lambda t: models.SparseVector(indices=[1, 2], values=[0.5, 0.5]),
    )
    kb_tool = tools.make_kb_tools([kb])[0]
    out = kb_tool.invoke({"query": "保修", "kb_id": kb})
    import json

    data = json.loads(out)
    assert data.get("fallback")
    assert data["results"]
