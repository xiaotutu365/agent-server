"""回归测试：Agent 配置变更后必须清理 AGENT_CACHE（聊天页恒带 agent_id 走缓存路径）。

背景 bug：PUT /api/admin/agents/{id}、set-default、delete 三处热重建只重建全局 AGENT，
不清 AGENT_CACHE["agent:{id}"]，导致聊天页（恒带 agent_id）永远使用陈旧 agent 实例，
表现为「保存并热重建」后 MCP 工具列表仍不更新（bugs/mcp-agent-cache-stale/bug.md）。

运行：
  cd backend && ./venv/Scripts/python.exe -m pytest tests/test_agent_cache_invalidation.py -q
"""

import asyncio

import main
from main import AgentConfig


def _fake_build(counter):
    async def build_agent(cfg, system_prompt=None):
        counter.append(1)
        return {"built": len(counter)}
    return build_agent


def _prep(monkeypatch):
    """隔离外部依赖：不真正构建 agent，不碰数据库。"""
    counter = []
    import agent.deep_agent as da
    monkeypatch.setattr(da, "build_agent", _fake_build(counter))
    monkeypatch.setattr(main, "load_default_config", lambda: asyncio.sleep(0, result={}))
    monkeypatch.setattr(main, "REBUILD_LOCK", asyncio.Lock())
    monkeypatch.setattr(main, "AGENT_CACHE_LOCK", asyncio.Lock())
    main.AGENT_CACHE.clear()
    return counter


def test_get_agent_for_caches_by_agent_id(monkeypatch):
    """基线：同 agent_id 两次请求只构建一次（缓存生效）。"""
    counter = _prep(monkeypatch)

    async def scenario():
        cfg = {"id": "a1", "is_default": False}
        monkeypatch.setattr(main, "get_agent", lambda aid: asyncio.sleep(0, result=dict(cfg)))
        first = await main.get_agent_for(None, "a1")
        second = await main.get_agent_for(None, "a1")
        return first, second, len(counter)

    first, second, builds = asyncio.run(scenario())
    assert first is second, "同 agent_id 应命中缓存返回同一实例"
    assert builds == 1, f"应只构建一次，实际 {builds} 次"
    main.AGENT_CACHE.clear()


def test_put_agent_evicts_cache(monkeypatch):
    """PUT 更新 Agent 后，AGENT_CACHE 中该 agent 条目必须失效。"""
    counter = _prep(monkeypatch)

    async def scenario():
        cfg = {"id": "default", "is_default": True, "mcp_servers": []}
        monkeypatch.setattr(main, "update_agent",
                            lambda aid, body: asyncio.sleep(0, result=dict(cfg)))
        # 预置陈旧缓存条目（模拟 bug 场景：缓存里是旧实例）
        stale = {"STALE": True}
        main.AGENT_CACHE["agent:default"] = stale
        await main.update_admin_agent("default", AgentConfig(id="default"), {})
        return main.AGENT_CACHE.get("agent:default")

    entry = asyncio.run(scenario())
    main.AGENT_CACHE.clear()
    assert entry is None or "STALE" not in entry, f"PUT 热重建后缓存仍为陈旧实例：{entry}"


def test_set_default_evicts_cache(monkeypatch):
    """set-default 后，该 agent 的缓存条目必须失效。"""
    counter = _prep(monkeypatch)

    async def scenario():
        cfg = {"id": "a2", "is_default": True, "mcp_servers": []}
        monkeypatch.setattr(main, "update_agent",
                            lambda aid, body: asyncio.sleep(0, result=dict(cfg)))
        main.AGENT_CACHE["agent:a2"] = {"STALE": True}
        await main.set_default_agent("a2", {})
        return main.AGENT_CACHE.get("agent:a2")

    entry = asyncio.run(scenario())
    main.AGENT_CACHE.clear()
    assert entry is None or "STALE" not in entry, f"set-default 后缓存仍陈旧：{entry}"


def test_delete_agent_evicts_cache(monkeypatch):
    """delete 后，被删 agent 的缓存条目必须失效。"""
    counter = _prep(monkeypatch)

    async def scenario():
        monkeypatch.setattr(main, "delete_agent",
                            lambda aid: asyncio.sleep(0, result={"rebuild": False}))
        main.AGENT_CACHE["agent:a3"] = {"STALE": True}
        await main.delete_admin_agent("a3", {})
        return main.AGENT_CACHE.get("agent:a3")

    entry = asyncio.run(scenario())
    main.AGENT_CACHE.clear()
    assert entry is None or "STALE" not in entry, f"delete 后缓存仍陈旧：{entry}"
