"""重新入库：上传留档 + POST /api/kb/{kb_id}/documents/reingest 契约测试（202 异步，SPEC-kb-ocr-ingest C2）。

留档：上传成功后原文件保存到 data/uploads/{kb_id}/{source}，供重新入库取用。
重新入库：建任务 → worker 提取成功后主进程删旧建新（失败旧片段保留）。
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kb.ingest as ingest
import kb.tasks as tasks
from kb.api import router

KB = "t_reingest"
CONTENT = "# 退货政策\n七天无理由退货。\n\n# 保修条款\n整机保修一年。"


@pytest.fixture(autouse=True)
def inline_runner(monkeypatch):
    monkeypatch.setattr(tasks, "RUNNER", "inline")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "UPLOADS_ROOT", str(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _upload(client, name="policy.md", content=CONTENT):
    r = client.post(
        f"/api/kb/{KB}/documents",
        files={"file": (name, content, "text/markdown")},
    )
    assert r.status_code == 202
    t = client.get(f"/api/kb/ingest-tasks/{r.json()['task_id']}").json()
    assert t["status"] == "done", f"任务应完成：{t}"
    return t


def _reingest(client, file):
    r = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": file})
    assert r.status_code == 202
    body = r.json()
    assert body["file"] == file and body["kb_id"] == KB
    t = client.get(f"/api/kb/ingest-tasks/{body['task_id']}").json()
    assert t["status"] == "done", f"任务应完成：{t}"
    return t


def test_upload_archives_original(client):
    _upload(client)
    archived = os.path.join(ingest.UPLOADS_ROOT, KB, "policy.md")
    assert os.path.isfile(archived)
    with open(archived, encoding="utf-8") as f:
        assert "七天无理由退货" in f.read()


def test_reingest_rebuilds_same_chunks(client):
    initial = _upload(client)["chunks"]
    data = _reingest(client, "policy.md")
    assert data["chunks"] == initial
    # 重建后片段可检索到，来源不变
    from kb import retrieval

    docs = retrieval.hybrid_search(KB, "保修")
    assert any(d.metadata["source"] == "policy.md" for d in docs)


def test_reingest_replaces_old_chunks(client):
    """连续重建不累积：片段数与首次入库一致（删旧建新，point id 确定性保证同 id 覆盖）。"""
    initial = _upload(client)["chunks"]
    assert _reingest(client, "policy.md")["chunks"] == initial
    assert _reingest(client, "policy.md")["chunks"] == initial


def test_reingest_no_archive_404(client):
    _upload(client)
    r = client.post(f"/api/kb/{KB}/documents/reingest", params={"file": "ghost.md"})
    assert r.status_code == 404
    assert "留档" in r.json()["detail"]


def test_reingest_missing_kb_404(client):
    r = client.post("/api/kb/no_such_kb/documents/reingest", params={"file": "a.md"})
    assert r.status_code == 404
