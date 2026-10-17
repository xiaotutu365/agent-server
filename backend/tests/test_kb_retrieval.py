from qdrant_client import models
import uuid

import kb.config as cfg
from kb import store, retrieval


def _seed(kb_id, text):
    store.create_kb(kb_id)
    pt = models.PointStruct(
        id=str(uuid.uuid4()),
        vector={
            cfg.DENSE_NAME: [0.1] * cfg.EMBEDDING_DIM,
            cfg.SPARSE_NAME: models.SparseVector(indices=[1, 2], values=[0.5, 0.5]),
        },
        payload={"text": text, "source": "doc.txt", "kb_id": kb_id, "chunk_idx": 0},
    )
    store.upsert_points(kb_id, [pt])


def test_hybrid_search_returns_seeded():
    _seed("retrieval_test", "退货政策：七天内无理由退货。")
    docs = retrieval.hybrid_search("retrieval_test", "退货", top_k=3)
    assert len(docs) >= 1
    assert "退货" in docs[0].page_content


def test_isolation_between_kbs():
    _seed("kb_a", "A专属内容zzz")
    _seed("kb_b", "B专属内容yyy")
    docs = retrieval.hybrid_search("kb_a", "A专属", top_k=5)
    assert docs, "应检索到 kb_a 的内容"
    assert all(d.metadata.get("kb_id") == "kb_a" for d in docs)
    assert not any("yyy" in d.page_content for d in docs)


def test_search_returns_rrf_scores():
    _seed("score_test", "评分测试内容qqq")
    docs = retrieval.hybrid_search("score_test", "评分", top_k=3)
    assert docs, "应检索到内容"
    scores = [d.metadata.get("score") for d in docs]
    assert all(isinstance(x, (int, float)) for x in scores), "每条结果都应带 score"
    assert scores == sorted(scores, reverse=True), "score 应降序"


def test_runtime_param_override():
    _seed("override_test", "参数覆盖测试www")
    docs = retrieval.hybrid_search("override_test", "参数", top_k=1, candidate=1, rrf_k=1)
    assert len(docs) <= 1, "candidate=1 时结果不超过 1 条"
    if docs:
        assert docs[0].metadata["score"] >= 0.5, "rrf_k=1 时 rank0 单路得分 1/2"
