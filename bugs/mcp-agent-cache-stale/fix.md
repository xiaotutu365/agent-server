# 修复记录：mcp-agent-cache-stale

## 根因

`main.py` 中 Agent 配置的三处热重建端点（`PUT /api/admin/agents/{agent_id}`、
`POST .../set-default`、`DELETE .../{agent_id}`）只重建全局 `AGENT`，
不清理 `AGENT_CACHE[f"agent:{agent_id}"]`。

前端聊天请求恒带 `agent_id`，`get_agent_for()` 命中陈旧缓存条目，
导致「保存并热重建」对聊天页不生效——本例中缓存条目建立时 demo 服务器（crm_ping/add）
未加载成功，此后聊天页永远看不到 crm_ping，而后台「测试连接」（discover，独立建连）始终正常。

## 改动范围

- `backend/main.py`
  - `update_admin_agent`：热重建后 `AGENT_CACHE.clear()`（按 system_prompt 缓存的条目内嵌默认 Agent 配置，一并失效）
  - `set_default_agent`：同上
  - `delete_admin_agent`：`AGENT_CACHE.pop(f"agent:{agent_id}", None)`
- `backend/tests/test_agent_cache_invalidation.py`（新增回归测试，4 用例）

## 回归测试

- red：修复前 3 个失效用例失败（PUT/set-default/delete 后缓存仍为陈旧实例）
- green：修复后 `test_agent_cache_invalidation.py` + `test_mcp_gate.py` 共 5 passed

## 验证结果（2026-10-16）

1. 重启后端（加载修复代码，清空陈旧缓存）。
2. 走 UI 相同路径（POST /api/chat/stream 带 agent_id="default"，admin 登录）：
   - echo → `[echo] final-echo` ✅
   - crm_ping → `[MCP] pong: final-ping` ✅
3. 顺带还原测试数据基线：test-suite 的 `allow_roles` 恢复为空（场景 C 遗留）。

## 备注

- 文档 `docs/MCP_UI_TEST_STEPS.md` 场景 B 本身无误；用户页面失败是本 bug 所致。
  已在文档「常见坑」补充该问题说明（修复需重启后端一次生效）。
