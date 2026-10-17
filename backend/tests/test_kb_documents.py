"""T2 文档管理：GET/DELETE /api/kb/{kb_id}/documents 契约测试。

不依赖 embedding：直接用 store.upsert_points 造点（维度取当前 settings）。
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
    """一个已入库两份文档（a.md 2 片段、b.md 1 片段）的知识库，测完删除。"""
    kb_id = "t_doc_test"
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
        _point("p3", "b.md", 0, "丙文档片段"),
    ])
    yield kb_id
    store.drop_kb(kb_id)


def test_list_documents_aggregates_by_source(client, kb):
    r = client.get(f"/api/kb/{kb}/documents")
    assert r.status_code == 200
    docs = {d["file"]: d for d in r.json()["documents"]}
    assert docs["a.md"]["chunks"] == 2
    assert docs["a.md"]["size_chars"] == len("第一段内容甲") + len("第二段内容乙")
    assert docs["b.md"]["chunks"] == 1


def test_delete_document_removes_only_that_source(client, kb):
    r = client.delete(f"/api/kb/{kb}/documents", params={"file": "a.md"})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2

    docs = {d["file"]: d for d in client.get(f"/api/kb/{kb}/documents").json()["documents"]}
    assert "a.md" not in docs
    assert "b.md" in docs


def test_delete_missing_document_404(client, kb):
    r = client.delete(f"/api/kb/{kb}/documents", params={"file": "ghost.md"})
    assert r.status_code == 404


def test_documents_on_missing_kb_404(client):
    assert client.get("/api/kb/no_such_kb/documents").status_code == 404
    r = client.delete("/api/kb/no_such_kb/documents", params={"file": "a.md"})
    assert r.status_code == 404


def test_delete_document_invalid_kb_id_400(client):
    r = client.delete("/api/kb/bad%20id/documents", params={"file": "a.md"})
    assert r.status_code == 400
