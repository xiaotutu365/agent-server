"""L8 检索调优：加权 RRF（vector_weight）+ 相似度阈值（similarity_threshold）。

契约（SPEC-knowledge-base.md 能力 L8）：
- vector_weight：dense 路贡献 w/(k+rank+1)，sparse 路贡献 (1-w)/(k+rank+1)；默认 0.5 等价现行为
- similarity_threshold：rerank 分优先，否则 dense cosine 分；纯 sparse 召回（无 cosine 分）的
  片段保留；dense 降级（纯 BM25）整体跳过过滤；threshold=0 不过滤（现行为）
- save_settings 校验：vector_weight ∈ [0,1]、similarity_threshold ≥ 0，非法 ValueError（API 400）
"""

import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import models

import kb.config as cfg
import kb.settings as kb_settings
from kb import retrieval, store
from kb.api import router


# ---------- 加权 RRF（单元级） ----------

def _hit(i):
    return SimpleNamespace(id=f"h{i}", payload={"text": f"t{i}"}, score=1.0)


def test_rrf_weight_full_dense():
    """w=1：纯 dense 排序，sparse 路不贡献。"""
    dense = [_hit(1), _hit(2)]  # dense: h1 rank0, h2 rank1
    sparse = [_hit(2), _hit(1)]  # sparse: h2 rank0, h1 rank1
    fused = retrieval._rrf([dense, sparse], k=60, weights=[1.0, 0.0])
    order = [h.id for h, _ in fused]
    assert order == ["h1", "h2"], "w=1 时应按 dense 路排名"
    assert fused[0][1] == pytest.approx(1 / 61), "w=1 时 rank0 得分 1/(k+1)"


def test_rrf_weight_full_sparse():
    """w=0：纯 sparse 排序。"""
    dense = [_hit(1), _hit(2)]
    sparse = [_hit(2), _hit(1)]
    fused = retrieval._rrf([dense, sparse], k=60, weights=[0.0, 1.0])
    assert [h.id for h, _ in fused] == ["h2", "h1"]


def test_rrf_half_weight_equals_unweighted_order():
    """w=0.5：各路同乘 0.5，相对序与现行为（无权重）一致。"""
    dense = [_hit(1), _hit(2), _hit(3)]
    sparse = [_hit(2), _hit(3)]
    old = retrieval._rrf([dense, sparse], k=60)
    new = retrieval._rrf([dense, sparse], k=60, weights=[0.5, 0.5])
    assert [h.id for h, _ in old] == [h.id for h, _ in new]
    # 分数等比例减半
    for (_, s1), (_, s2) in zip(old, new):
        assert s2 == pytest.approx(s1 / 2)


def test_rrf_no_weights_backward_compatible():
    """weights=None：与旧签名行为一致。"""
    dense = [_hit(1), _hit(2)]
    sparse = [_hit(2)]
    fused = retrieval._rrf([dense, sparse], k=60)
    # h1: dense rank0 = 1/61；h2: dense rank1 + sparse rank0 = 1/62 + 1/61（最高分在前）
    assert fused[0][0].id == "h2"
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


# ---------- 阈值过滤（单元级 _apply_threshold） ----------

def test_threshold_filters_low_cosine_keeps_sparse_only():
    """无 rerank：cosine 低于阈值滤除；无 cosine 分（纯 sparse 召回）保留。"""
    h_cos_high = _hit(1)
    h_cos_low = _hit(2)
    h_sparse_only = _hit(3)
    ranked = [(h_cos_high, 0.05), (h_cos_low, 0.04), (h_sparse_only, 0.03)]
    dense_scores = {"h1": 0.9, "h2": 0.2}  # h3 无 cosine 分
    out = retrieval._apply_threshold(ranked, dense_scores, {}, threshold=0.5)
    assert {h.id for h, _ in out} == {"h1", "h3"}, "低 cosine 滤除，纯 sparse 保留"


def test_threshold_zero_is_noop():
    ranked = [(_hit(1), 0.01)]
    out = retrieval._apply_threshold(ranked, {"h1": 0.01}, {}, threshold=0.0)
    assert len(out) == 1


def test_threshold_uses_rerank_scores_when_present():
    """有 rerank 分时以 rerank 分为准（而非 cosine）。"""
    ranked = [(_hit(1), 0.05), (_hit(2), 0.04)]
    rerank_scores = {"h1": 0.9, "h2": 0.1}
    out = retrieval._apply_threshold(ranked, {"h1": 0.1, "h2": 0.1}, rerank_scores, threshold=0.5)
    assert {h.id for h, _ in out} == {"h1"}


# ---------- 集成：种子库 + 固定向量控制 cosine ----------

def _seed_vec(kb_id, source, dense_vec, sparse_idx, text):
    store.create_kb(kb_id)
    pt = models.PointStruct(
        id=str(uuid.uuid4()),
        vector={
            cfg.DENSE_NAME: dense_vec,
            cfg.SPARSE_NAME: models.SparseVector(
                indices=sparse_idx, values=[0.5] * len(sparse_idx)
            ),
        },
        payload={"text": text, "source": source, "kb_id": kb_id, "chunk_idx": 0},
    )
    store.upsert_points(kb_id, [pt])


E1 = [1.0] + [0.0] * (cfg.EMBEDDING_DIM - 1)  # 查询向量
E2 = [0.0, 1.0] + [0.0] * (cfg.EMBEDDING_DIM - 2)  # 与 E1 正交，cosine=0


def test_threshold_filters_low_cosine_end_to_end(monkeypatch):
    _seed_vec("t_thresh", "high.md", E1, [1], "高相关内容")
    _seed_vec("t_thresh", "low.md", E2, [2], "低相关内容")
    monkeypatch.setattr(
        "kb.embed.embed_query",
        lambda t: (E1, models.SparseVector(indices=[1, 2], values=[0.5, 0.5])),
    )
    docs = retrieval.hybrid_search("t_thresh", "高相关", top_k=5, similarity_threshold=0.5)
    sources = {d.metadata.get("source") for d in docs}
    assert "high.md" in sources
    assert "low.md" not in sources, "cosine=0 的片段应被阈值滤除"

    docs_all = retrieval.hybrid_search("t_thresh", "高相关", top_k=5)
    assert {d.metadata.get("source") for d in docs_all} == {"high.md", "low.md"}, \
        "threshold=0（默认）不过滤，现行为不变"


def test_threshold_skipped_when_dense_falls_back(monkeypatch):
    """dense 降级纯 BM25 时整体跳过过滤，保兜底可用性。"""
    _seed_vec("t_fb_thresh", "a.md", E1, [1], "保修内容")
    monkeypatch.setattr("kb.embed.embed_query", lambda t: (_ for _ in ()).throw(ConnectionError("x")))
    monkeypatch.setattr(
        "kb.embed.sparse_query",
        lambda t: models.SparseVector(indices=[1], values=[0.5]),
    )
    docs = retrieval.hybrid_search("t_fb_thresh", "保修", top_k=5, similarity_threshold=0.99)
    assert docs, "降级路径不应被阈值清空"
    assert all(d.metadata.get("fallback") for d in docs)


def _fake_rerank(monkeypatch):
    """monkeypatch 默认 rerank 模型与 HTTP 响应：按片段文本打分——含「G」0.9，含「B」0.1。"""
    import json

    monkeypatch.setattr(
        "agent.model_store.get_default_sync",
        lambda kind: {"model": "rr", "base_url": "http://rr.local", "api_key": "k"}
        if kind == "rerank" else None,
    )

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        body = json.loads(req.data.decode())
        results = [
            {"index": i, "relevance_score": 0.9 if "G" in doc else 0.1}
            for i, doc in enumerate(body["documents"])
        ]
        return Resp(json.dumps({"results": results}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_threshold_with_rerank_scores_end_to_end(monkeypatch):
    _seed_vec("t_rr_thresh", "good.md", E1, [1], "内容G")
    _seed_vec("t_rr_thresh", "bad.md", E1, [2], "内容B")
    monkeypatch.setattr(
        "kb.embed.embed_query",
        lambda t: (E1, models.SparseVector(indices=[1, 2], values=[0.5, 0.5])),
    )
    _fake_rerank(monkeypatch)
    docs = retrieval.hybrid_search("t_rr_thresh", "内容", top_k=5, similarity_threshold=0.5)
    sources = {d.metadata.get("source") for d in docs}
    assert "good.md" in sources
    assert "bad.md" not in sources, "rerank 分低于阈值应滤除（即使 cosine=1）"


# ---------- settings 校验 ----------

def test_save_settings_rejects_bad_vector_weight():
    with pytest.raises(ValueError):
        kb_settings.save_settings({"vector_weight": 1.5})
    with pytest.raises(ValueError):
        kb_settings.save_settings({"vector_weight": "abc"})


def test_save_settings_rejects_negative_threshold():
    with pytest.raises(ValueError):
        kb_settings.save_settings({"similarity_threshold": -0.1})


def test_save_settings_accepts_valid_tuning_values():
    s = kb_settings.save_settings({"vector_weight": 0.3, "similarity_threshold": 0.2})
    assert s["vector_weight"] == 0.3
    assert s["similarity_threshold"] == 0.2
    kb_settings._settings = None
    s2 = kb_settings.get_settings()
    assert s2["vector_weight"] == 0.3 and s2["similarity_threshold"] == 0.2


def test_api_settings_tuning_roundtrip_and_400():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    assert client.put("/api/kb/settings", json={"vector_weight": 2}).status_code == 400
    assert client.put("/api/kb/settings", json={"similarity_threshold": -1}).status_code == 400

    r = client.put("/api/kb/settings", json={"vector_weight": 0.7, "similarity_threshold": 0.1})
    assert r.status_code == 200
    data = r.json()
    assert data["vector_weight"] == 0.7 and data["similarity_threshold"] == 0.1
