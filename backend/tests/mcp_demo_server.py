"""最小 MCP stdio 演示服务器（仅用于验证 agent 可消费外部 MCP 工具）。

暴露两个工具：
  - crm_ping(message): 回显消息，验证调用链路
  - add(a, b): 简单加法，验证带参工具

运行（由 agent 以 stdio 子进程方式拉起，无需手动启动）：
  本文件被 agent 的 mcp_servers 配置以
  {"transport":"stdio","command":"<venv>/python","args":["tests/mcp_demo_server.py"]} 调用。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-mcp")


@mcp.tool()
def crm_ping(message: str) -> str:
    """测试用 MCP 工具：回显一条消息，用于验证 agent 能调用外部 MCP 工具。"""
    return f"[MCP] pong: {message}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """两数相加。"""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
