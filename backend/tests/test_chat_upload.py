"""聊天窗口文件上传接口（SPEC-chat-ui-evoflow C3.1）：

- POST /api/chat/upload：multipart file → 保存至 workspace/uploads/
- 校验：未选文件/超 20MB/文件名不安全 → 400；未登录 → 401
- 文件名安全化：路径穿越拦截（../../ 等）
"""

import io

import pytest
from fastapi.testclient import TestClient

import main as app_main


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch):
    d = tmp_path / "uploads"
    monkeypatch.setattr(app_main, "UPLOAD_DIR", d)
    return d


@pytest.fixture()
def client(uploads_dir):
    app = app_main.app
    app.dependency_overrides[app_main.require_admin] = lambda: {
        "id": "admin-1", "role": "admin", "username": "admin",
    }
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _upload(client, filename, content):
    return client.post(
        "/api/chat/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def test_upload_saves_to_uploads_dir(client, uploads_dir):
    r = _upload(client, "notes.txt", "你好工作区".encode())
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "notes.txt"
    assert body["path"].startswith("uploads/")
    assert body["size"] == len("你好工作区".encode())
    saved = uploads_dir / "notes.txt"
    assert saved.read_text(encoding="utf-8") == "你好工作区"


def test_upload_same_name_gets_timestamp_suffix(client, uploads_dir):
    _upload(client, "a.txt", b"v1")
    r2 = _upload(client, "a.txt", b"v2")
    assert r2.status_code == 200
    assert r2.json()["name"] != "a.txt"
    assert (uploads_dir / "a.txt").read_bytes() == b"v1"
    assert r2.json()["size"] == 2


def test_upload_rejects_oversize(client, uploads_dir):
    big = b"x" * (20 * 1024 * 1024 + 1)
    r = _upload(client, "big.bin", big)
    assert r.status_code == 400
    assert not list(uploads_dir.glob("*"))


def test_upload_sanitizes_traversal_filename(client, uploads_dir):
    r = _upload(client, "../../etc/passwd", b"evil")
    assert r.status_code == 200
    body = r.json()
    assert "/" not in body["name"] and ".." not in body["name"]
    assert body["path"].startswith("uploads/")
    # 实际文件只落在 uploads 目录内
    saved = list(uploads_dir.glob("*passwd*"))
    assert len(saved) == 1


def test_upload_rejects_blank_filename(client, uploads_dir):
    # 全空白文件名：安全化后为空 → 400（空字符串 filename 在 multipart 层即被框架 422 拒绝）
    r = _upload(client, "   ", b"data")
    assert r.status_code == 400


def test_upload_requires_admin():
    app = app_main.app
    c = TestClient(app)
    r = c.post("/api/chat/upload", files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 401
