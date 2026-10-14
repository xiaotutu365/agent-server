"""MCP 测试服务：用于验证 agent 集成外部 MCP 工具的能力。

相比 mcp_demo_server.py（仅 crm_ping / add），本服务刻意覆盖更丰富的工具形态，
以便测试 agent 在以下维度的集成能力：

  - 多参数 + 多种基础类型（str / int / float / bool / list / dict）
  - 无参工具、带默认值参数工具
  - 返回类型多样（str / int / float / bool / list），考验结果解析
  - 异步工具（async def），考验 asyncio 调用链路
  - 故意失败的工具，考验 agent 的错误恢复
  - 结构化入参（对象/字典），考验结构化参数抽取

三种传输方式（由环境变量 MCP_TRANSPORT 切换，默认 stdio）：
  - stdio          ：由 agent 以子进程方式拉起，无需手动启动
  - sse            ：以 HTTP SSE 暴露，URL = http://MCP_HOST:MCP_PORT/sse
  - streamable_http：以 Streamable HTTP 暴露，URL = http://MCP_HOST:MCP_PORT/mcp

本地手动启动示例：
  # stdio（默认）
  <backend>/venv/bin/python tests/mcp_test_server.py

  # sse
  MCP_TRANSPORT=sse MCP_PORT=8001 <backend>/venv/bin/python tests/mcp_test_server.py

  # streamable_http
  MCP_TRANSPORT=streamable_http <backend>/venv/bin/python tests/mcp_test_server.py
"""

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-mcp-test-suite")


# ---------- 基础：回显 / 数学 / 无参 ----------

@mcp.tool()
def echo(text: str) -> str:
    """回显输入的文本，用于验证最简单的调用链路与参数传递。"""
    return f"[echo] {text}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """两个整数相加，用于验证带多个基础类型参数的工具调用。"""
    return a + b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """两个浮点数相乘，用于验证 float 参数与浮点返回值的处理。"""
    return a * b


@mcp.tool()
def get_server_uptime() -> str:
    """无参数工具：返回服务标识与时间戳，用于验证零参数工具的调用。"""
    return "agent-mcp-test-suite 在线"


# ---------- 复杂参数：列表 / 字典 / 默认值 ----------

@mcp.tool()
def concat(strings: list[str], separator: str = ", ") -> str:
    """将字符串列表用分隔符拼接，用于验证 list[str] 参数的抽取与默认值。"""
    return separator.join(strings)


@mcp.tool()
def search_items(keyword: str, limit: int = 3) -> list[str]:
    """模拟搜索：返回若干与关键词相关的条目，用于验证 list 返回值的解析。

    keyword 为查询关键词；limit 控制返回条数（默认 3）。
    """
    pool = [
        f"结果A-{keyword}",
        f"结果B-{keyword}",
        f"结果C-{keyword}",
        f"结果D-{keyword}",
        f"结果E-{keyword}",
    ]
    return pool[: max(0, min(limit, len(pool)))]


@mcp.tool()
def summarize_record(record: dict[str, Any]) -> str:
    """接收一个字典/对象，返回其键与摘要，用于验证结构化（object）参数的抽取。

    record 应为一个 JSON 对象，例如 {"name": "张三", "age": 30}。
    """
    if not isinstance(record, dict) or not record:
        return "收到的 record 为空或不是对象。"
    parts = [f"{k}={v}" for k, v in record.items()]
    return f"共 {len(record)} 个字段：{' ; '.join(parts)}"


# ---------- 布尔 / 字符串处理 ----------

@mcp.tool()
def is_even(n: int) -> bool:
    """判断整数是否为偶数，用于验证 bool 返回值的处理。"""
    return n % 2 == 0


@mcp.tool()
def reverse_text(text: str) -> str:
    """反转字符串，用于验证字符串处理类工具。"""
    return text[::-1]


# ---------- 异步工具 ----------

@mcp.tool()
async def fetch_quote() -> str:
    """异步工具：模拟一次异步获取（含短暂等待），用于验证 asyncio 调用链路。"""
    await asyncio.sleep(0.1)
    return "Stay hungry, stay foolish."


# ---------- 错误恢复测试 ----------

@mcp.tool()
def always_fail() -> str:
    """故意抛出异常的测试工具，用于验证 agent 在工具失败时的错误恢复能力。"""
    raise RuntimeError("MCP 测试工具被设计为必然失败（用于错误恢复测试）。")


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8001"))
        mcp.run(transport=transport, host=host, port=port)
