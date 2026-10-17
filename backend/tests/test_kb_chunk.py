"""引用原文查看：GET /api/kb/{kb_id}/chunk?source=&chunk_idx= 契约测试。

对话消息的引用 badge 点击后按 (kb_id, source, chunk_idx) 取片段原文。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import models

import kb.config as cfg
import kb.settings as kb_settings
from kb import store
from kb.api import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture()
def kb(tmp_path):
    kb_id = "t_chunk_test"
    store.drop_kb(kb_id)
    store.create_kb(kb_id)
    dim = kb_settings.get_settings()["embedding_dim"]
    vec = [0.1] * dim

    def _point(pid, source, idx, text):
        import uuid

        return models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{kb}-{pid}")),
            vector={cfg.DENSE_NAME: vec, cfg.SPARSE_NAME: models.SparseVector(indices=[1, 2], values=[0.5, 0.5])},
            payload={"text": text, "source": source, "kb_id": kb_id, "chunk_idx": idx},
        )

    store.upsert_points(kb_id, [
        _point("p1", "a.md", 0, "第一段内容甲"),
        _point("p2", "a.md", 1, "第二段内容乙"),
    ])
    yield kb_id
    store.drop_kb(kb_id)


def test_get_chunk_returns_text(client, kb):
    r = client.get(f"/api/kb/{kb}/chunk", params={"source": "a.md", "chunk_idx": 1})
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "第二段内容乙"
    assert data["source"] == "a.md"
    assert data["chunk_idx"] == 1
    assert data["kb_id"] == kb


def test_get_chunk_missing_404(client, kb):
    r = client.get(f"/api/kb/{kb}/chunk", params={"source": "a.md", "chunk_idx": 99})
    assert r.status_code == 404
    r = client.get(f"/api/kb/{kb}/chunk", params={"source": "ghost.md", "chunk_idx": 0})
    assert r.status_code == 404


def test_get_chunk_missing_kb_404(client):
    r = client.get("/api/kb/no_such_kb/chunk", params={"source": "a.md", "chunk_idx": 0})
    assert r.status_code == 404


def test_get_chunk_invalid_kb_id_400(client):
    r = client.get("/api/kb/bad%20id/chunk", params={"source": "a.md", "chunk_idx": 0})
    assert r.status_code == 400
