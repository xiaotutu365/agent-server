"""T6/L4：Agent 级知识库挂载（kb_ids）与工具闭包绑定。"""

import asyncio
import json

from agent import config_store
from agent.tool_registry import get_tool, resolve_tools


def _cfg(kb_ids):
    return {
        "tools_enabled": ["search_knowledge_base"],
        "kb_enabled": True,
        "kb_ids": kb_ids,
    }


def test_resolve_tools_binds_kb_ids():
    tools = resolve_tools(_cfg(["mount_a"]))
    kb_tools = [t for t in tools if t.name == "search_knowledge_base"]
    assert kb_tools, "kb_enabled 时应加载 kb 工具"
    t = kb_tools[0]
    # 挂载外的库应被拒绝
    out = t.invoke({"query": "随便", "kb_id": "mount_b"})
    assert "未挂载" in out
    # 全局注册表工具不受绑定影响（工具目录页仍展示原始工具）
    from agent.tool_registry import REGISTRY

    assert REGISTRY["search_knowledge_base"]["func"] is get_tool("search_knowledge_base")


def test_kb_ids_empty_keeps_global_behavior():
    """kb_ids=[] 保持旧行为：任意库可查（不存在的库返回空结果而非拒绝）。"""
    tools = resolve_tools(_cfg([]))
    t = [x for x in tools if x.name == "search_knowledge_base"][0]
    out = t.invoke({"query": "x", "kb_id": "definitely_missing_kb"})
    data = json.loads(out)
    assert data.get("results") == []


def test_multi_mount_cross_kb_search_order():
    """多库挂载且未指定 kb_id：跨库检索，结果按 score 降序合并（此处两库均空→空结果）。"""
    tools = resolve_tools(_cfg(["mount_x1", "mount_x2"]))
    t = [x for x in tools if x.name == "search_knowledge_base"][0]
    out = t.invoke({"query": "x"})
    data = json.loads(out)
    assert data.get("results") == []


def test_config_store_kb_ids_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "DB_PATH", str(tmp_path / "t.db"))
    created = asyncio.run(
        config_store.create_agent({"name": "t", "kb_enabled": True, "kb_ids": ["policy", "faq"]})
    )
    assert created["kb_ids"] == ["policy", "faq"]
    got = asyncio.run(config_store.get_agent(created["id"]))
    assert got["kb_ids"] == ["policy", "faq"]
    upd = asyncio.run(config_store.update_agent(created["id"], {"kb_ids": ["only1"]}))
    assert upd["kb_ids"] == ["only1"]


def test_extract_kb_citations():
    """kb 工具 JSON 输出 → SSE tool_end 的 citations 结构。"""
    from main import _extract_kb_citations

    out = json.dumps({
        "results": [
            {"content": "退货需 7 天内", "kb_id": "policy", "source": "policy.md",
             "chunk_idx": 2, "score": 0.031},
            {"content": "无来源条目", "kb_id": "policy", "source": "", "chunk_idx": 0},
        ]
    }, ensure_ascii=False)
    cits = _extract_kb_citations(out)
    assert cits == [{"file": "policy.md", "kb_id": "policy", "chunk_idx": 2, "score": 0.031}]

    # 错误输出 / 非 JSON / 空结果 → 空 citations
    assert _extract_kb_citations(json.dumps({"error": "未挂载知识库 x"})) == []
    assert _extract_kb_citations("工具不是 JSON 的普通输出") == []
    assert _extract_kb_citations(json.dumps({"results": []})) == []
