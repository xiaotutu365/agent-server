# Plan: MCP 测试服务套件（mcp-test-suite）

> 目标：提供一套更完整的 MCP 测试服务，用于验证 agent 集成外部 MCP 工具的能力
> （多参数/多类型、无参、list+默认值、结构化 dict 入参、bool 返回、异步、错误恢复），
> 并补齐自动化测试（冒烟 + allow_roles 越权闸集成测试）。
> 关联文档：`docs/MCP_GUIDE.md` §6（已更新）。

## 设计要点
- 测试服务复用现有 `FastMCP` + `@mcp.tool()` + `mcp.run()` 模式（与 `mcp_demo_server.py` 一致）。
- 同一份服务由环境变量 `MCP_TRANSPORT`（默认 stdio）切换 `stdio` / `sse` / `streamable_http`，
  覆盖 `docs/MCP_GUIDE.md` §2 列出的三种传输。
- 越权闸集成测试不引入新依赖（`pytest-asyncio` 未安装）：用同步测试函数 + `asyncio.run()` 包裹，
  真实拉起 `mcp_test_server` 子进程（复用 `sys.executable`），断言 `allow_roles` 拦截行为。

## 涉及文件
```
backend/tests/mcp_test_server.py        # 新增：测试 MCP 服务器（11 工具 + 三传输）
backend/tests/test_mcp_test_server.py   # 新增：冒烟测试（工具注册校验）
backend/tests/test_mcp_gate.py          # 新增：allow_roles 越权闸集成测试
docs/MCP_GUIDE.md                       # 更新：§6 测试服务章节
```

## 验证检查点
- Checkpoint 1：冒烟测试通过（静态校验 11 工具注册）。
- Checkpoint 2：越权闸集成测试通过（user 被拦截、admin 放行）。
- Checkpoint 3：`pytest tests/test_mcp_*.py -q` 全绿。
