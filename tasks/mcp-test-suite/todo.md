# Todo: MCP 测试服务套件（mcp-test-suite）

> 状态：✅ 实现与测试已完成，待人工在开发机跑 `pytest` 复核。

## Phase 1 — 测试服务与工具

- [x] **T1 新增 mcp_test_server.py**
  - 验收：暴露 11 个工具；`MCP_TRANSPORT` 可切换 stdio/sse/streamable_http。
  - 验证：`python tests/mcp_test_server.py` 可启动（stdio）；`MCP_TRANSPORT=sse` 可监听。
  - 文件：`backend/tests/mcp_test_server.py`

- [x] **T2 新增冒烟测试 test_mcp_test_server.py**
  - 验收：`EXPECTED_TOOLS` 全部被注册（issubset 且集合相等）。
  - 验证：`python -m pytest tests/test_mcp_test_server.py -q` 通过。
  - 文件：`backend/tests/test_mcp_test_server.py`

## Phase 2 — 越权闸集成测试

- [x] **T3 新增 test_mcp_gate.py**
  - 验收：`allow_roles=["admin"]` 下，user 角色调 `echo` 返回 `⛔ 无权限`；admin 角色返回 `[echo] hi`。
  - 验证：`python -m pytest tests/test_mcp_gate.py -q` 通过（需 venv 具备 mcp/fastmcp）。
  - 文件：`backend/tests/test_mcp_gate.py`

- [x] **T4 更新 docs/MCP_GUIDE.md §6**
  - 验收：新增「更完整的 MCP 测试服务」章节（工具能力表、三传输命令、接入配置、自动化测试）。
  - 验证：人工审阅文档章节编号衔接（原 §6 顺延为 §7）。
  - 文件：`docs/MCP_GUIDE.md`

## Checkpoint — 端到端复核（需人工在 Linux/macOS 开发机执行）
- [ ] `cd backend && ./venv/bin/python -m pytest tests/test_mcp_test_server.py tests/test_mcp_gate.py -q` 全绿。
- [ ] 后台「工具」页用 stdio 配置接入，点「测试连接」提示暴露 11 个工具。
- [ ] 聊天页以 user/admin 分别调 `always_fail` / `echo` 观察闸行为。
