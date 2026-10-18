"""记忆模块 M5：管理 API 契约（require_admin + 手动添加/启停/删除联动向量）。"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.auth
from memory import api as memory_api
from memory import store as mstore
from memory import vector as mvector


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mstore, "DB_PATH", str(tmp_path / "test.db"))
    asyncio.run(mstore.init_memories_table())
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(memory_api.router)
    app.dependency_overrides[agent.auth.require_admin] = lambda: {
        "id": "admin-1", "role": "admin", "username": "admin",
    }
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_post_creates_and_vectorized(client):
    r = client.post("/api/memory", json={"content": "用户偏好简洁回答"})
    assert r.status_code == 200
    m = r.json()["memory"]
    assert m["content"] == "用户偏好简洁回答"
    assert m["source_thread"] == "manual"
    assert mvector.search("admin-1", "回答风格") != [], "手动添加的记忆应可被向量检索"


def test_post_rejects_empty(client):
    assert client.post("/api/memory", json={"content": "   "}).status_code == 400


def test_post_survives_vector_failure(client, monkeypatch):
    """向量写入失败（embedding 不可用等）不 500——记忆本体已入库（bug: memory-add-fails）。"""
    def boom(entry):
        raise ConnectionError("embedding 不可用")
    monkeypatch.setattr(mvector, "upsert_memory", boom)
    r = client.post("/api/memory", json={"content": "向量写入失败但记忆仍在"})
    assert r.status_code == 200
    items = client.get("/api/memory").json()["memories"]
    assert [m["content"] for m in items] == ["向量写入失败但记忆仍在"]


def test_post_offloads_vector_to_thread(client, monkeypatch):
    """向量调用放线程池执行：工作线程内无 running loop，不阻塞事件循环。"""
    seen = {}
    def probe(entry):
        try:
            asyncio.get_running_loop()
            seen["blocking"] = True  # 事件循环线程内同步执行（bug 行为）
        except RuntimeError:
            seen["offloaded"] = True  # to_thread 工作线程（期望）
    monkeypatch.setattr(mvector, "upsert_memory", probe)
    client.post("/api/memory", json={"content": "offload probe"})
    assert seen.get("offloaded") and not seen.get("blocking")


def test_get_list_with_filters(client):
    client.post("/api/memory", json={"content": "记忆 A"})
    m2 = client.post("/api/memory", json={"content": "记忆 B"}).json()["memory"]
    client.put(f"/api/memory/{m2['id']}/enabled", json={"enabled": False})

    all_items = client.get("/api/memory").json()["memories"]
    assert len(all_items) == 2
    assert [m["content"] for m in client.get(
        "/api/memory", params={"enabled": False}).json()["memories"]] == ["记忆 B"]
    assert client.get("/api/memory", params={"user_id": "nope"}).json()["memories"] == []


def test_put_enabled_404(client):
    assert client.put("/api/memory/nope/enabled", json={"enabled": True}).status_code == 404


def test_delete_forgets_sqlite_and_vector(client):
    m = client.post("/api/memory", json={"content": "用户偏好简洁回答"}).json()["memory"]
    assert client.delete(f"/api/memory/{m['id']}").status_code == 200
    assert asyncio.run(mstore.list_memories()) == []
    assert mvector.search("admin-1", "回答风格") == []
    assert client.delete(f"/api/memory/{m['id']}").status_code == 404


def test_requires_admin():
    """无凭证访问管理端点 → 401。"""
    app = FastAPI()
    app.include_router(memory_api.router)
    c = TestClient(app)
    assert c.get("/api/memory").status_code == 401
    assert c.post("/api/memory", json={"content": "x"}).status_code == 401
