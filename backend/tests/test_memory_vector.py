"""记忆模块 M2：Qdrant `memories` collection 向量检索（dense-only，复用 kb 客户端）。"""

import asyncio

import pytest

import kb.embed as embed
from memory import store as mstore
from memory import vector


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mstore, "DB_PATH", str(tmp_path / "test.db"))
    asyncio.run(mstore.init_memories_table())
    yield


def _seed(user_id, content):
    m = asyncio.run(mstore.add_memory(user_id, content))
    vector.upsert_memory(m)
    return m


def test_upsert_and_search():
    _seed("u1", "用户偏好简洁回答")
    hits = vector.search("u1", "回答风格", top_k=5)
    assert len(hits) == 1
    assert hits[0]["content"] == "用户偏好简洁回答"
    assert hits[0]["user_id"] == "u1"


def test_search_filters_user_and_enabled():
    m1 = _seed("u1", "记忆 A")
    _seed("u2", "记忆 B")
    vector.update_enabled(m1["id"], False)
    hits = vector.search("u1", "任意", top_k=5)
    assert hits == [], "本人停用的记忆与其他用户的记忆都不应召回"
    vector.update_enabled(m1["id"], True)
    hits = vector.search("u1", "任意", top_k=5)
    assert [h["content"] for h in hits] == ["记忆 A"]


def test_search_without_collection_returns_empty():
    assert vector.search("u1", "任意") == []


def test_search_embed_failure_degrades(monkeypatch):
    _seed("u1", "记忆 A")

    def boom(text):
        raise RuntimeError("embedding 服务不可达")

    monkeypatch.setattr(embed, "embed_query", boom)
    assert vector.search("u1", "任意") == []


def test_delete_points():
    m = _seed("u1", "记忆 A")
    assert len(vector.search("u1", "任意")) == 1
    vector.delete_points(m["id"])
    assert vector.search("u1", "任意") == []
