"""MCP 角色闸示例测试：5 条身份数据，2 条有权限、3 条无权限。

示例设定：把 tests/mcp_test_server.py 的 echo 工具当成一个「敏感 MCP 服务器」，
在服务器描述里配 allow_roles=["admin"]，即只有管理员能调用。

随后以 5 种不同身份（user_ctx_var 里的 role）调用 echo，断言：
  - 有权限（role=admin）        -> 返回真实结果 "[echo] hi"
  - 无权限（user / 无上下文 / 自定义角色）-> 返回 "⛔ 无权限..."，工具不执行

5 条数据见下方 CASES（2 allow / 3 deny）。数据即「身份样例」，对应生产里
不同 role 的用户；本层网关只认 user_ctx 里的 role 字符串，不查数据库。

运行：
  cd backend && ./venv/bin/python -m pytest tests/test_mcp_permission_demo.py -v
"""

import asyncio
import os
import sys

import pytest

from agent.mcp_tools import load_mcp_tools, set_user_ctx

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.join(_HERE, "mcp_test_server.py")

# ---------------- 5 条示例数据：2 条有权限，3 条无权限 ----------------
CASES = [
    # ===== 有权限（命中 allow_roles=['admin']）=====
    {
        "id": "u-admin-1001", "name": "张管理员", "role": "admin", "expect": "allow",
        "desc": "系统管理员，role=admin 命中白名单",
    },
    {
        "id": "u-admin-1002", "name": "李主管", "role": "admin", "expect": "allow",
        "desc": "另一名管理员，同样命中白名单",
    },
    # ===== 无权限 =====
    {
        "id": "u-user-2001", "name": "王普通用户", "role": "user", "expect": "deny",
        "desc": "普通用户，role=user 不在白名单",
    },
    {
        "id": None, "name": "匿名请求", "role": None, "expect": "deny",
        "desc": "未经过鉴权，user_ctx 为空，按无权限处理",
    },
    {
        "id": "u-custom-3001", "name": "赵审计", "role": "auditor", "expect": "deny",
        "desc": "自定义角色（非 admin），演示非 admin 一律拒绝",
    },
]


async def _run_case(uid, role):
    servers = [{
        "name": "test-suite",
        "transport": "stdio",
        "enabled": True,
        "command": sys.executable,
        "args": [_SERVER],
        "allow_roles": ["admin"],   # 仅管理员可调用此服务器
    }]
    tools, _ = await load_mcp_tools(servers, apply_policy=True)
    echo = next((t for t in tools if t.name == "echo"), None)
    assert echo is not None, "未从测试服务器加载到 echo 工具"
    set_user_ctx(uid, role)
    return await echo.ainvoke({"text": "hi"})


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_mcp_role_gate(case):
    res = asyncio.run(_run_case(case["id"], case["role"]))
    if case["expect"] == "allow":
        assert res == "[echo] hi", f"[{case['name']}] 有权限却未返回真实结果：{res}"
    else:
        assert "⛔ 无权限" in res, f"[{case['name']}] 无权限却放行了：{res}"
