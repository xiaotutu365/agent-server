"""记忆模块 M4：chat SSE 注入（SystemMessage 前插）与 done 后后台抽取接线。"""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import SystemMessage

import main
from memory import extract as memory_extract
from memory import store as mstore
from memory import vector as mvector

AUTH = {"id": "u9", "role": "user", "username": "tester"}


class FakeAgent:
    def __init__(self):
        self.inputs = None

    async def astream_events(self, inputs, config=None, version=None):
        self.inputs = inputs
        yield {"event": "on_chat_model_stream", "name": "m",
               "data": {"chunk": SimpleNamespace(content="你好呀")}}

    async def aget_state(self, config):
        return None


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mstore, "DB_PATH", str(tmp_path / "test.db"))
    asyncio.run(mstore.init_memories_table())
    yield


@pytest.fixture()
def client(monkeypatch):
    fake = FakeAgent()

    async def fake_get_agent_for(system_prompt, agent_id=None, model_id=None):
        return fake

    monkeypatch.setattr(main, "get_agent_for", fake_get_agent_for)
    main.app.dependency_overrides[main.get_current_user] = lambda: dict(AUTH)
    yield TestClient(main.app), fake
    main.app.dependency_overrides.clear()


def _events(text: str) -> list:
    """解析 SSE 文本为 [(event, data)]。"""
    out = []
    for block in text.split("event: "):
        if not block.strip():
            continue
        head, _, data = block.partition("data: ")
        out.append((head.strip(), data.strip()))
    return out


def test_injects_memory_as_system_message(client):
    tc, fake = client
    m = asyncio.run(mstore.add_memory("u9", "用户偏好简洁回答", source_thread="t0"))
    mvector.upsert_memory(m)

    r = tc.post("/api/chat/stream", json={"message": "我喜欢什么回答风格", "thread_id": "t1"})
    assert r.status_code == 200
    assert "done" in [e for e, _ in _events(r.text)]
    msgs = fake.inputs["messages"]
    assert isinstance(msgs[0], SystemMessage)
    assert "已知记忆" in msgs[0].content and "用户偏好简洁回答" in msgs[0].content
    assert msgs[1] == {"role": "user", "content": "我喜欢什么回答风格"}


def test_no_memory_no_system_message(client):
    tc, fake = client
    tc.post("/api/chat/stream", json={"message": "你好", "thread_id": "t1"})
    msgs = fake.inputs["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"


def test_extraction_scheduled_after_done(client, monkeypatch):
    tc, _ = client
    called = threading.Event()
    captured = {}

    async def fake_extract(user_id, thread_id, user_text, assistant_text):
        captured.update(user_id=user_id, thread_id=thread_id,
                        user_text=user_text, assistant_text=assistant_text)
        called.set()

    monkeypatch.setattr(memory_extract, "extract_and_save", fake_extract)

    tc.post("/api/chat/stream", json={"message": "记住我喜欢简洁回答", "thread_id": "t1"})
    assert called.wait(2), "done 后应调度记忆抽取任务"
    assert captured == {
        "user_id": "u9", "thread_id": "t1",
        "user_text": "记住我喜欢简洁回答", "assistant_text": "你好呀",
    }


def test_resume_skips_extraction(client, monkeypatch):
    tc, _ = client
    m = asyncio.run(mstore.add_memory("u9", "用户偏好简洁回答"))
    mvector.upsert_memory(m)
    called = threading.Event()

    async def fake_extract(*a, **kw):
        called.set()

    monkeypatch.setattr(memory_extract, "extract_and_save", fake_extract)

    r = tc.post("/api/chat/stream", json={"thread_id": "t1", "resume": {"decisions": []}})
    assert r.status_code == 200
    assert not called.wait(0.3), "HITL 恢复路径不应触发抽取"
