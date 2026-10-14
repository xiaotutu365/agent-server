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
