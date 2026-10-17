"""记忆模块 M3：对话后 LLM 抽取记忆（JSON 陈述句，0-3 条，任何异常静默）。"""

import asyncio
from types import SimpleNamespace

import pytest

from memory import extract, store as mstore


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mstore, "DB_PATH", str(tmp_path / "test.db"))
    asyncio.run(mstore.init_memories_table())
    yield


def _fake_llm(reply: str):
    class FakeLLM:
        def invoke(self, prompt):
            return SimpleNamespace(content=reply)

    async def _get():
        return FakeLLM()

    return _get


async def _saved():
    return await mstore.list_memories()


def test_extract_saves_statements(monkeypatch):
    monkeypatch.setattr(extract, "_get_llm", _fake_llm('["用户偏好简洁的回答", "用户在开发一个 agent 平台"]'))
    asyncio.run(extract.extract_and_save("u1", "t1", "我喜欢简洁的回答", "好的，我会注意。"))
    items = asyncio.run(_saved())
    assert [m["content"] for m in items] == \
        ["用户在开发一个 agent 平台", "用户偏好简洁的回答"]  # 最新在前
    assert all(m["source_thread"] == "t1" for m in items)


def test_extract_caps_at_three(monkeypatch):
    monkeypatch.setattr(extract, "_get_llm", _fake_llm('["一", "二", "三", "四", "五"]'))
    asyncio.run(extract.extract_and_save("u1", "t1", "用户", "助手"))
    assert len(asyncio.run(_saved())) == 3


def test_extract_no_memory_outputs_empty(monkeypatch):
    monkeypatch.setattr(extract, "_get_llm", _fake_llm("[]"))
    asyncio.run(extract.extract_and_save("u1", "t1", "你好", "你好！"))
    assert asyncio.run(_saved()) == []


def test_extract_garbled_output_silent(monkeypatch):
    monkeypatch.setattr(extract, "_get_llm", _fake_llm("我觉得没什么值得记住的。"))
    asyncio.run(extract.extract_and_save("u1", "t1", "你好", "你好！"))
    assert asyncio.run(_saved()) == []


def test_extract_llm_error_silent(monkeypatch):
    class BoomLLM:
        def invoke(self, prompt):
            raise RuntimeError("LLM 配额耗尽")

    async def _get():
        return BoomLLM()

    monkeypatch.setattr(extract, "_get_llm", _get)
    asyncio.run(extract.extract_and_save("u1", "t1", "你好", "你好！"))
    assert asyncio.run(_saved()) == []


def test_extract_without_default_llm_skips(monkeypatch):
    async def _get():
        return None

    monkeypatch.setattr(extract, "_get_llm", _get)
    asyncio.run(extract.extract_and_save("u1", "t1", "你好", "你好！"))
    assert asyncio.run(_saved()) == []


def test_get_llm_falls_back_to_env_model(monkeypatch):
    """model_store 无默认 llm 时，回退 agent 环境变量（与 deep_agent 同链）。"""
    import agent.model_store as ms

    async def _none(t="llm"):
        return None

    monkeypatch.setattr(ms, "get_default", _none)
    monkeypatch.setenv("MODEL_NAME", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    captured = {}

    def fake_init(model, **kw):
        captured.update(model=model, **kw)
        return "LLM-SENTINEL"

    import langchain.chat_models as lcm
    monkeypatch.setattr(lcm, "init_chat_model", fake_init)

    llm = asyncio.run(extract._get_llm())
    assert llm == "LLM-SENTINEL"
    assert captured["model"] == "env-model"


def test_get_llm_prefers_model_store_default(monkeypatch):
    import agent.model_store as ms

    async def _store(t="llm"):
        return {"model": "store-model", "api_key": "sk-store", "base_url": "https://x/v1"}

    monkeypatch.setattr(ms, "get_default", _store)
    captured = {}

    def fake_init(model, **kw):
        captured.update(model=model, **kw)
        return "LLM-SENTINEL"

    import langchain.chat_models as lcm
    monkeypatch.setattr(lcm, "init_chat_model", fake_init)

    asyncio.run(extract._get_llm())
    assert captured["model"] == "store-model"
    assert captured["api_key"] == "sk-store"


def test_parse_json_array_wrapped_in_markdown():
    assert extract._parse_json_array('```json\n["用户喜欢 A"]\n```') == ["用户喜欢 A"]
    assert extract._parse_json_array('前缀 ["a"] 后缀') == ["a"]
    assert extract._parse_json_array("没有数组") == []
    assert extract._parse_json_array('[1, "a"]') == ["a"], "非字符串条目被过滤"
