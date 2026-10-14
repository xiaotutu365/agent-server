"""MCP 客户端：把外部 MCP 服务器（stdio / SSE / Streamable HTTP）暴露的工具
并入本 agent 的工具集，无需改代码即可扩展能力。

服务器在 agent 配置 mcp_servers 中以字典描述；build_agent 时统一加载。

越界保护（与 CRM 工具一致的「不越界」模型）：
  - 每个服务器可配 allow_roles（如 ["admin"]），调用时按当前用户角色做闸，
    越权直接返回「⛔ 无权限」，工具不会被真正执行。
  - 当前用户身份（user_id / role）写入上下文（user_ctx_var），供后续透传给 MCP
    服务器做服务端归属校验（HTTP 传输可在服务器配置里用 headers 下发令牌）。

注意：MCP 工具的鉴权最终由对应 MCP 服务器自行负责；本层做的是「调用前闸」，
防止越权用户触达敏感工具。
"""

import contextvars
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# 持有活动客户端引用，防止其内部 session 被 GC（工具闭包依赖这些 session）
_LIVE_CLIENTS: list = []

# 当前请求的用户身份；由 main.chat_stream 在每次对话开始时写入，
# 工具调用发生时读取，用于越界判断。基于 ContextVar，按请求任务隔离。
user_ctx_var: contextvars.ContextVar = contextvars.ContextVar("mcp_user_ctx", default=None)


def set_user_ctx(user_id: Any, role: str) -> None:
    """写入当前请求用户身份（在 chat_stream 里调用）。"""
    user_ctx_var.set({"user_id": str(user_id), "role": role})


def _server_entry(s: dict) -> dict:
    """把单个服务器描述转换为 MultiServerMCPClient 的连接配置项。"""
    entry: dict[str, Any] = {"transport": s.get("transport", "stdio")}
    if entry["transport"] == "stdio":
        entry["command"] = s["command"]
        entry["args"] = s.get("args", [])
        if s.get("env"):
            entry["env"] = s["env"]
    else:  # sse / streamable_http
        entry["url"] = s["url"]
        if s.get("headers"):
            entry["headers"] = s["headers"]
    return entry


def _wrap_tool(tool, server_name: str, allow_roles: list | None):
    """按 allow_roles 包装 MCP 工具：越权时拒绝，否则委托原工具执行。"""

    schema = getattr(tool, "args_schema", None)
    if not allow_roles or schema is None:
        return tool

    async def _guarded(**kwargs):
        ctx = user_ctx_var.get() or {}
        role = ctx.get("role")
        if role not in allow_roles:
            return (
                f"⛔ 无权限：MCP 服务器「{server_name}」的工具仅允许角色 "
                f"{allow_roles} 调用，当前角色为 {role}。"
            )
        return await tool.ainvoke(kwargs)

    return StructuredTool.from_function(
        name=tool.name,
        description=tool.description or "",
        args_schema=schema,
        coroutine=_guarded,
    )


async def load_mcp_tools(servers: list[dict], apply_policy: bool = True):
    """加载所有启用的 MCP 服务器工具。

    返回 (tools, None)。单个服务器连接/握手失败时记录告警并跳过，不阻断其余。
    不使用 async with 上下文管理器，以免退出时关闭 session——保持连接常驻，
    供后续对话中反复调用工具。

    apply_policy=False 时跳过角色闸（用于后台「预览工具」等仅列举场景）。
    """
    out: list = []
    for s in servers or []:
        if not s.get("enabled", True):
            continue
        name = s.get("name") or s.get("id") or f"mcp{len(out)}"
        try:
            client = MultiServerMCPClient({"__s": _server_entry(s)})
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP 服务器 %s 连接失败，已跳过：%s", name, exc)
            continue
        _LIVE_CLIENTS.append(client)
        allow = s.get("allow_roles") if apply_policy else None
        for t in tools:
            out.append(_wrap_tool(t, name, allow))
        logger.info("MCP 服务器 %s 加载 %d 个工具（allow_roles=%s）", name, len(tools), allow)
    return out, None
