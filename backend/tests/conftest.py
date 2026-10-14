"""测试夹具：内存版 Qdrant + mock embedding，无需外部服务/网络。"""

import pytest
from qdrant_client import QdrantClient, models

import kb.config as cfg
import kb.embed as embed
from kb import store


@pytest.fixture(autouse=True)
def memory_qdrant():
    store._client = QdrantClient(":memory:")
    yield
    store._client = None


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    def fake_query(text):
        return [0.1] * cfg.EMBEDDING_DIM, models.SparseVector(
            indices=[1, 2], values=[0.5, 0.5]
        )

    def fake_docs(texts):
        dense = [[0.1] * cfg.EMBEDDING_DIM for _ in texts]
        sparse = [models.SparseVector(indices=[1], values=[0.5]) for _ in texts]
        return dense, sparse

    monkeypatch.setattr(embed, "embed_query", fake_query)
    monkeypatch.setattr(embed, "embed_documents", fake_docs)
