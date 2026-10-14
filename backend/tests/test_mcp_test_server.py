"""mcp_test_server 的冒烟测试：验证所有测试工具都被正确注册。

运行：
  cd backend && ./venv/bin/python -m pytest tests/test_mcp_test_server.py -q

（本测试仅静态加载模块、检查工具注册，不真正拉起 MCP 服务，
 因此无需网络或外部服务；与 mcp_demo_server 的集成验证见 docs/MCP_GUIDE.md）
"""

import asyncio
import importlib.util
import os

SERVER_PATH = os.path.join(os.path.dirname(__file__), "mcp_test_server.py")

EXPECTED_TOOLS = {
    "echo",
    "add",
    "multiply",
    "get_server_uptime",
    "concat",
    "search_items",
    "summarize_record",
    "is_even",
    "reverse_text",
    "fetch_quote",
    "always_fail",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("mcp_test_server", SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tool_names(mcp) -> set[str]:
    """兼容不同 fastmcp 版本获取已注册工具名。"""
    if hasattr(mcp, "list_tools"):
        try:
            tools = asyncio.run(mcp.list_tools())
            return {t.name for t in tools}
        except Exception:
            pass
    tm = getattr(mcp, "_tool_manager", None)
    if tm is not None and hasattr(tm, "list_tools"):
        return {t.name for t in tm.list_tools()}
    raise RuntimeError("无法从 fastmcp 实例获取工具列表")


def test_all_expected_tools_registered():
    mod = _load_module()
    names = _tool_names(mod.mcp)
    missing = EXPECTED_TOOLS - names
    assert not missing, f"以下工具未被注册：{missing}"
    # 额外确认没有意外多出/缺失
    assert names == EXPECTED_TOOLS
