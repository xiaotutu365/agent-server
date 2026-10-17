"""记忆模块 M1：memories 表 CRUD（SQLite，复用 agent 库）。"""

import pytest

from memory import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    yield


@pytest.fixture()
def inited(tmp_db):
    import asyncio
    asyncio.run(store.init_memories_table())
    yield


def test_add_memory_returns_entry(inited):
    m = asyncio_run_add()
    assert m["content"] == "用户偏好简洁的回答"
    assert m["user_id"] == "u1"
    assert m["memory_type"] == "semantic"
    assert m["enabled"] is True
    assert m["source_thread"] == "t1"
    assert m["id"] and m["created_at"]


def asyncio_run_add():
    import asyncio
    return asyncio.run(store.add_memory("u1", "用户偏好简洁的回答", source_thread="t1"))


def test_list_memories_filters(inited):
    import asyncio
    asyncio.run(store.add_memory("u1", "记忆 A"))
    asyncio.run(store.add_memory("u2", "记忆 B"))
    m3 = asyncio.run(store.add_memory("u1", "记忆 C"))
    asyncio.run(store.set_enabled(m3["id"], False))

    assert len(asyncio.run(store.list_memories())) == 3
    assert [m["content"] for m in asyncio.run(store.list_memories(user_id="u1"))] == \
        ["记忆 C", "记忆 A"]  # 最新在前
    assert [m["content"] for m in asyncio.run(store.list_memories(enabled=False))] == ["记忆 C"]


def test_set_enabled(inited):
    import asyncio
    m = asyncio.run(store.add_memory("u1", "记忆 A"))
    updated = asyncio.run(store.set_enabled(m["id"], False))
    assert updated["enabled"] is False
    assert asyncio.run(store.set_enabled("no-such-id", True)) is None


def test_forget_memory(inited):
    import asyncio
    m = asyncio.run(store.add_memory("u1", "记忆 A"))
    assert asyncio.run(store.forget_memory(m["id"])) is True
    assert asyncio.run(store.list_memories()) == []
    assert asyncio.run(store.forget_memory("no-such-id")) is False
