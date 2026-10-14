"""集成测试：验证 agent/mcp_tools 的 allow_roles 越权闸。

真实拉起 mcp_test_server（stdio 子进程）作为外部 MCP 服务，挂 allow_roles=["admin"]，
然后以不同角色调用工具，断言：
  - 越权角色（user）被闸拦截，工具不真正执行，返回「⛔ 无权限」
  - 授权角色（admin）放行，工具正常执行并返回真实结果

运行：
  cd backend && ./venv/bin/python -m pytest tests/test_mcp_gate.py -q

依赖：运行 pytest 的 python 须具备 mcp/fastmcp（同一 venv），
子进程复用 sys.executable 启动测试服务器，无需手动启动。
"""

import asyncio
import os
import sys

from agent.mcp_tools import load_mcp_tools, set_user_ctx

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.join(_HERE, "mcp_test_server.py")


async def _run_gate() -> tuple[str, str]:
    servers = [{
        "name": "test-suite",
        "transport": "stdio",
        "enabled": True,
        "command": sys.executable,
        "args": [_SERVER],
        "allow_roles": ["admin"],
    }]
    tools, _ = await load_mcp_tools(servers, apply_policy=True)
    echo = next((t for t in tools if t.name == "echo"), None)
    assert echo is not None, "未从测试服务器加载到 echo 工具"

    # 越权角色：应被闸拦截
    set_user_ctx("u1", "user")
    denied = await echo.ainvoke({"text": "hi"})

    # 授权角色：应正常执行
    set_user_ctx("a1", "admin")
    ok = await echo.ainvoke({"text": "hi"})

    return denied, ok


def test_allow_roles_gate():
    denied, ok = asyncio.run(_run_gate())
    assert "⛔ 无权限" in denied, f"越权未被拦截，返回：{denied}"
    assert ok == "[echo] hi", f"授权调用结果异常，返回：{ok}"
