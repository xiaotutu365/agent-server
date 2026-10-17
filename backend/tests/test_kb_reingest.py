"""重新入库：上传留档 + POST /api/kb/{kb_id}/documents/reingest 契约测试。

留档：上传成功后原文件保存到 data/uploads/{kb_id}/{source}，供重新入库取用。
重新入库：删除旧片段 → 按当前分片策略从留档重建。
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kb.ingest as ingest
from kb.api import router

KB = "t_reingest"
CONTENT = "# 退货政策\n七天无理由退货。\n\n# 保修条款\n整机保修一年。"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "UPLOADS_ROOT", str(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _upload(client):
    return client.post(
        f"/api/kb/{KB}/documents",
        files={"file": ("policy.md", CONTENT, "text/markdown")},
    )


def test_upload_archives_original(client):
    r = _upload(client)
    assert r.status_code == 200
    archived = os.path.join(ingest.UPLOADS_ROOT, KB, "policy.md")
    assert os.path.isfile(archived)
    with open(archived, encoding="utf-8") as f:
        assert "七天无理由退货" in f.read()


def test_reingest_rebuilds_same_chunks(client):
    assert _upload(client).status_code == 200
    initial = _upload(client).json()["chunks"]

    r = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": "policy.md"})
    assert r.status_code == 200
    data = r.json()
    assert data["file"] == "policy.md"
    assert data["chunks"] == initial
    # 重建后片段可检索到，来源不变
    from kb import retrieval

    docs = retrieval.hybrid_search(KB, "保修")
    assert any(d.metadata["source"] == "policy.md" for d in docs)


def test_reingest_replaces_old_chunks(client):
    """连续重建不累积：片段数与首次入库一致（删旧建新，point id 确定性保证同 id 覆盖）。"""
    initial = _upload(client).json()["chunks"]
    r1 = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": "policy.md"})
    r2 = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": "policy.md"})
    assert r1.json()["chunks"] == r2.json()["chunks"] == initial


def test_reingest_no_archive_404(client):
    assert _upload(client).status_code == 200
    r = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": "ghost.md"})
    assert r.status_code == 404
    assert "留档" in r.json()["detail"]


def test_reingest_missing_kb_404(client):
    r = client.post("/api/kb/no_such_kb/documents/reingest", params={"file": "a.md"})
    assert r.status_code == 404
