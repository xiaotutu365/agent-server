"""会话级模型选择：thread_meta 存储层 + build_agent/get_agent_for 模型覆盖链路。

Spec：docs/specs/SPEC-session-model-select.md
- thread_meta：会话覆盖模型的 set/get/delete（lg_thread 带用户前缀，天然按用户隔离）
- build_agent：model_id 非空时用 get_model(model_id) 替代 get_default("llm")，extra 参数同样生效
- get_agent_for：缓存键扩展 {原key}::model:{model_id}；model_id 为空时键与既有行为完全一致

运行：
  cd backend && ./venv/bin/python -m pytest tests/test_session_model.py -q
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import agent.thread_meta as thread_meta  # noqa: E402
import agent.deep_agent as da  # noqa: E402
import main  # noqa: E402


# ── thread_meta 存储层 ────────────────────────────────────────────────

@pytest.fixture
def tmp_meta_db(tmp_path, monkeypatch):
    db = str(tmp_path / "session_model.db")
    monkeypatch.setattr(thread_meta, "DB_PATH", db)
    return db


def test_thread_meta_set_get_delete(tmp_meta_db):
    """set 后可读回；delete 后为 None；不同会话互不影响。"""

    async def run():
        await thread_meta.set_thread_model("u1:t-a", "m-1")
        await thread_meta.set_thread_model("u1:t-b", "m-2")
        assert await thread_meta.get_thread_model("u1:t-a") == "m-1"
        assert await thread_meta.get_thread_model("u1:t-b") == "m-2"
        # 覆盖写：同一会话再 set 更新
        await thread_meta.set_thread_model("u1:t-a", "m-3")
        assert await thread_meta.get_thread_model("u1:t-a") == "m-3"
        # 未设置过的会话返回 None
        assert await thread_meta.get_thread_model("u1:t-none") is None
        # 删除后返回 None，且不影响其他会话
        await thread_meta.delete_thread_meta("u1:t-a")
        assert await thread_meta.get_thread_model("u1:t-a") is None
        assert await thread_meta.get_thread_model("u1:t-b") == "m-2"

    asyncio.run(run())


def test_thread_meta_delete_missing_ok(tmp_meta_db):
    """删除不存在的记录不报错（幂等）。"""

    async def run():
        await thread_meta.delete_thread_meta("u9:none")

    asyncio.run(run())


# ── build_agent 模型解析（_resolve_llm_config）───────────────────────

def _patch_store(monkeypatch, *, default=None, by_id=None):
    """隔离 model_store：不碰真实 agent_sessions.db。"""
    from agent import model_store

    async def fake_get_default(t):
        return default

    async def fake_get_model(mid):
        return (by_id or {}).get(mid)

    monkeypatch.setattr(model_store, "get_default", fake_get_default)
    monkeypatch.setattr(model_store, "get_model", fake_get_model)


def test_resolve_llm_config_model_override(tmp_path, monkeypatch):
    """model_id 非空 → 使用指定模型条目（而非默认），api_key/base_url 随条目。"""
    _patch_store(
        monkeypatch,
        default={"model": "default-model", "api_key": "k-def", "base_url": "https://def", "extra": {}},
        by_id={"m-x": {"model": "target-model", "api_key": "k-x", "base_url": "https://x", "extra": {}}},
    )

    async def run():
        return await da._resolve_llm_config({}, model_id="m-x")

    name, key, url, params = asyncio.run(run())
    assert name == "target-model"
    assert key == "k-x"
    assert url == "https://x"


def test_resolve_llm_config_extra_params_from_override(tmp_path, monkeypatch):
    """覆盖模型的 extra 高级参数（temperature 等）应生效。"""
    _patch_store(
        monkeypatch,
        default={"model": "default-model", "api_key": "k-def", "base_url": "https://def", "extra": {}},
        by_id={"m-x": {"model": "target-model", "api_key": "k-x", "base_url": "https://x",
                       "extra": {"temperature": 0.9, "max_tokens": 512}}},
    )

    async def run():
        return await da._resolve_llm_config({}, model_id="m-x")

    _, _, _, params = asyncio.run(run())
    assert params["temperature"] == 0.9
    assert params["max_tokens"] == 512


def test_resolve_llm_config_fallback_default(tmp_path, monkeypatch):
    """model_id 为空 → 沿用现状：默认 llm 条目 > 环境变量。"""
    _patch_store(
        monkeypatch,
        default={"model": "default-model", "api_key": "k-def", "base_url": "https://def", "extra": {}},
    )
    monkeypatch.setenv("MODEL_NAME", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env")

    async def run():
        return await da._resolve_llm_config({}, model_id=None)

    name, key, url, _ = asyncio.run(run())
    assert name == "default-model"
    assert key == "k-def"


def test_resolve_llm_config_no_store_no_env(tmp_path, monkeypatch):
    """model_store 无任何配置 → 回退环境变量；环境变量也缺 → 不抛异常。"""
    _patch_store(monkeypatch, default=None)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    async def run():
        return await da._resolve_llm_config({}, model_id=None)

    name, _, _, _ = asyncio.run(run())
    assert name  # 至少有内置兜底名，不抛异常


def test_resolve_llm_config_override_missing_falls_back(tmp_path, monkeypatch):
    """model_id 指定的条目不存在（已被删除）→ 回退默认链路，不抛异常。"""
    _patch_store(
        monkeypatch,
        default={"model": "default-model", "api_key": "k-def", "base_url": "https://def", "extra": {}},
        by_id={},
    )

    async def run():
        return await da._resolve_llm_config({}, model_id="m-gone")

    name, key, url, _ = asyncio.run(run())
    assert name == "default-model"
    assert key == "k-def"


# ── get_agent_for 缓存键 ─────────────────────────────────────────────

def _fake_build(counter):
    async def build_agent(cfg, system_prompt=None, model_id=None):
        counter.append(model_id)
        return {"built": len(counter), "model_id": model_id}
    return build_agent


def _prep(monkeypatch):
    counter = []
    import agent.deep_agent as da
    monkeypatch.setattr(da, "build_agent", _fake_build(counter))
    monkeypatch.setattr(main, "load_default_config",
                        lambda: asyncio.sleep(0, result={}))
    monkeypatch.setattr(main, "AGENT_CACHE_LOCK", asyncio.Lock())
    main.AGENT_CACHE.clear()
    return counter


def test_get_agent_for_cache_key_includes_model(monkeypatch):
    """同一 agent_id 不同 model_id → 各自构建、互不复用；同 key 命中缓存。"""
    counter = _prep(monkeypatch)

    async def scenario():
        monkeypatch.setattr(main, "get_agent",
                            lambda aid: asyncio.sleep(0, result={"id": aid}))
        a_default = await main.get_agent_for(None, "a1")
        b_default = await main.get_agent_for(None, "a1")
        with_m1 = await main.get_agent_for(None, "a1", "m-1")
        with_m1_again = await main.get_agent_for(None, "a1", "m-1")
        with_m2 = await main.get_agent_for(None, "a1", "m-2")
        return a_default, b_default, with_m1, with_m1_again, with_m2

    a, b, m1, m1b, m2 = asyncio.run(scenario())
    main.AGENT_CACHE.clear()
    assert a is b, "model_id 为空时应命中既有缓存（键不变）"
    assert m1 is m1b, "同 model_id 应命中缓存"
    assert m1 is not m2 and m1 is not a, "不同模型不得复用实例"
    assert counter == [None, "m-1", "m-2"], f"构建次数应为 3 次，实际 {counter}"
    assert m1["model_id"] == "m-1", "build_agent 应收到模型覆盖参数"


def test_get_agent_for_default_path_with_model(monkeypatch):
    """无 prompt/agent 但带 model_id → 不返回全局 AGENT，而是按模型构建。"""
    counter = _prep(monkeypatch)

    async def scenario():
        got = await main.get_agent_for(None, None, "m-9")
        return got

    got = asyncio.run(scenario())
    main.AGENT_CACHE.clear()
    assert got == {"built": 1, "model_id": "m-9"}, "带模型覆盖时必须按模型构建新实例"


# ── 会话覆盖解析（_resolve_session_model）＋ 接口层 ──────────────────

@pytest.fixture
def tmp_store_db(tmp_path, monkeypatch):
    """model_store / deep_agent 的 DB 均指向临时库。"""
    from agent import model_store

    db = str(tmp_path / "models.db")
    monkeypatch.setattr(model_store, "DB_PATH", db)
    monkeypatch.setattr(da, "DB_PATH", str(tmp_path / "threads.db"))
    return db


async def _seed_model(mtype="llm", dim=0):
    from agent import model_store

    return await model_store.create_model({
        "name": f"cfg-{mtype}", "type": mtype, "base_url": "https://x",
        "model": "test-model", "api_key": "k", "dim": dim,
    })


def test_resolve_session_model_valid_persists(tmp_store_db, tmp_meta_db):
    """请求携带有效 llm 模型 → 返回该 id 并写入会话覆盖。"""

    async def run():
        m = await _seed_model()
        got = await main._resolve_session_model("u1:t1", m["id"])
        stored = await thread_meta.get_thread_model("u1:t1")
        return got, stored

    got, stored = asyncio.run(run())
    assert got == stored, "实际生效模型应与持久化覆盖一致"


def test_resolve_session_model_deleted_cleans(tmp_store_db, tmp_meta_db):
    """会话覆盖的模型已被删除 → 回退默认并清理覆盖记录。"""

    async def run():
        m = await _seed_model()
        await thread_meta.set_thread_model("u1:t1", m["id"])
        from agent import model_store
        await model_store.delete_model(m["id"])
        got = await main._resolve_session_model("u1:t1", None)
        stored = await thread_meta.get_thread_model("u1:t1")
        return got, stored

    got, stored = asyncio.run(run())
    assert got is None, "覆盖模型已删应回退默认"
    assert stored is None, "失效覆盖记录应被清理"


def test_resolve_session_model_empty_clears(tmp_store_db, tmp_meta_db):
    """显式传空串（前端「默认（跟随全局）」）→ 清除覆盖。"""

    async def run():
        await thread_meta.set_thread_model("u1:t1", "m-any")
        got = await main._resolve_session_model("u1:t1", "")
        stored = await thread_meta.get_thread_model("u1:t1")
        return got, stored

    got, stored = asyncio.run(run())
    assert got is None and stored is None, "空串应清除覆盖并跟随默认"


def test_resolve_session_model_rejects_non_llm(tmp_store_db, tmp_meta_db):
    """非 llm 类型（如 embedding）视为无效 → 回退默认并清理。"""

    async def run():
        m = await _seed_model(mtype="embedding", dim=8)
        got = await main._resolve_session_model("u1:t1", m["id"])
        stored = await thread_meta.get_thread_model("u1:t1")
        return got, stored

    got, stored = asyncio.run(run())
    assert got is None and stored is None, "非对话模型不得作为会话覆盖"


def test_list_threads_returns_model_id(tmp_store_db, tmp_meta_db, monkeypatch):
    """会话列表每项携带 model_id（无覆盖为空串）。"""
    import aiosqlite

    # checkpoints 表由 deep_agent 建在 da.DB_PATH；此处手工建最小表供 list_threads 查询
    async def _seed_thread(tid, ckpt):
        async with aiosqlite.connect(da.DB_PATH) as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints "
                "(thread_id TEXT, checkpoint_id TEXT, metadata TEXT, "
                "parent_checkpoint_id TEXT, type TEXT, checkpoint BLOB, writes BLOB)")
            await conn.execute(
                "INSERT INTO checkpoints (thread_id, checkpoint_id) VALUES (?,?)",
                (tid, ckpt))
            await conn.commit()

    class FakeAgent:
        async def aget_state(self, cfg):
            return None

    async def run():
        await _seed_thread("u1:t-a", "c1")
        await _seed_thread("u1:t-b", "c2")
        m = await _seed_model()
        await thread_meta.set_thread_model("u1:t-a", m["id"])
        monkeypatch.setattr(main, "AGENT", FakeAgent())
        resp = await main.list_threads({"id": 1, "role": "user"})
        return {t["thread_id"]: t for t in resp["threads"]}

    threads = asyncio.run(run())
    assert threads["t-a"]["model_id"], "有覆盖的会话应返回 model_id"
    assert threads["t-b"]["model_id"] == "", "无覆盖会话 model_id 应为空串"


def test_delete_thread_cascades_meta(tmp_store_db, tmp_meta_db, monkeypatch):
    """删除会话须级联清理 thread_meta。"""

    class FakeCheckpointer:
        def __init__(self):
            self.deleted = []

        async def adelete_thread(self, lg):
            self.deleted.append(lg)

    class FakeAgent:
        checkpointer = FakeCheckpointer()

    async def run():
        await thread_meta.set_thread_model("u1:t-x", "m-1")
        fake = FakeAgent()
        monkeypatch.setattr(main, "AGENT", fake)
        await main.delete_thread("t-x", {"id": 1, "role": "user"})
        stored = await thread_meta.get_thread_model("u1:t-x")
        return FakeAgent.checkpointer.deleted, stored

    deleted, stored = asyncio.run(run())
    assert deleted == ["u1:t-x"]
    assert stored is None, "删除会话应级联清理覆盖记录"


def test_list_chat_models_sanitized(tmp_store_db):
    """GET /api/models/chat：普通用户可访问；仅 llm 条目；不含 api_key/base_url。"""

    async def run():
        llm = await _seed_model()
        await _seed_model(mtype="embedding", dim=8)
        resp = await main.list_chat_models({"id": 2, "role": "user"})
        return llm, resp

    llm, resp = asyncio.run(run())
    models = resp["models"]
    assert [m["id"] for m in models] == [llm["id"]], "只应返回对话模型条目"
    for m in models:
        assert not ({"api_key", "base_url"} & set(m)), f"不得泄露敏感字段: {m}"
        assert {"id", "name", "model", "is_default"} <= set(m)


def test_admin_model_update_clears_cache(tmp_store_db, monkeypatch):
    """模型配置更新后 AGENT_CACHE 必须清空（含 ::model: 键的实例）。"""
    main.AGENT_CACHE["agent:a1"] = {"STALE": True}
    main.AGENT_CACHE["default::model:m-1"] = {"STALE": True}

    async def run():
        async def fake_update(mid, body):
            return {"id": mid, "type": "llm"}
        monkeypatch.setattr(main, "update_model", fake_update)
        await main.admin_update_model("m-1", {}, {"role": "admin"})

    asyncio.run(run())
    stale = dict(main.AGENT_CACHE)
    main.AGENT_CACHE.clear()
    assert not stale, f"模型更新后缓存仍残留: {list(stale)}"


def test_admin_model_delete_clears_cache(tmp_store_db, monkeypatch):
    """模型删除后 AGENT_CACHE 必须清空。"""
    main.AGENT_CACHE["default::model:m-1"] = {"STALE": True}

    async def run():
        async def fake_delete(mid):
            return {"deleted": mid}
        monkeypatch.setattr(main, "delete_model", fake_delete)
        await main.admin_delete_model("m-1", {"role": "admin"})

    asyncio.run(run())
    stale = dict(main.AGENT_CACHE)
    main.AGENT_CACHE.clear()
    assert not stale, f"模型删除后缓存仍残留: {list(stale)}"


def test_chat_stream_wires_session_model(tmp_store_db, tmp_meta_db, monkeypatch):
    """端到端布线：chat_stream 解析会话模型并传给 get_agent_for。"""
    import agent.mcp_tools as mcp_tools
    import memory.vector as memory_vector

    captured = {}

    class FakeAgent:
        def astream_events(self, inputs, config=None, version=None):
            async def gen():
                yield {"event": "on_chat_model_stream",
                       "name": "m", "data": {"chunk": type("C", (), {"content": "hi"})()}}
            return gen()

        async def aget_state(self, cfg):
            return None

    async def fake_get_agent_for(system_prompt, agent_id=None, model_id=None):
        captured["model_id"] = model_id
        return FakeAgent()

    monkeypatch.setattr(main, "get_agent_for", fake_get_agent_for)
    monkeypatch.setattr(memory_vector, "search",
                        lambda uid, q, k: [])
    monkeypatch.setattr(mcp_tools, "set_user_ctx", lambda uid, role: None)
    monkeypatch.setattr(main.memory_extract, "extract_and_save",
                        lambda *a, **k: asyncio.sleep(0, result=None))

    async def run():
        m = await _seed_model()
        req = main.ChatRequest(message="hello", thread_id="t1", model_id=m["id"])
        resp = await main.chat_stream(req, {"id": 1, "role": "user"})
        frames = []
        async for chunk in resp.body_iterator:
            frames.append(chunk)
        await asyncio.sleep(0)  # 让后台记忆抽取任务排空
        stored = await thread_meta.get_thread_model("u1:t1")
        body = "".join(c.decode() if isinstance(c, bytes) else c for c in frames)
        return captured.get("model_id"), stored, body

    model_id, stored, body = asyncio.run(run())
    assert model_id, "chat_stream 必须把解析后的模型传给 get_agent_for"
    assert stored == model_id, "发送消息时应持久化会话覆盖"
    assert "event: done" in body
