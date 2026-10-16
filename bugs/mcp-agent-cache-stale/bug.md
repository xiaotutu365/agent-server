# Bug：Agent 配置热重建后，聊天页仍使用陈旧 AGENT_CACHE（MCP 工具缺失）

## 现象

按 `docs/MCP_UI_TEST_STEPS.md` 场景 B 在聊天页测试：

- 第 2–3 步调用 `echo`（test-suite 服务器）→ 成功，返回 `[echo] hello-mcp`
- 第 4–5 步调用 `crm_ping`（demo 服务器）→ Agent 回复「我没有 crm_ping 这个工具」，
  只列出内置 CRM 工具（query_customer / list_customer_orders / create_work_order / crm_report）

后台「MCP 服务器」页「测试连接」两台均正常（discover 不经过聊天用的 agent 实例）。

## 复现步骤

1. 后端运行中，UI 聊天页发一条消息（此时 `AGENT_CACHE["agent:default"]` 被建立；
   若建立时 demo 服务器未加载成功，则该缓存实例永久缺 crm_ping）。
2. 后台改任意 Agent 配置并点「保存并热重建」（PUT /api/admin/agents/{id}）。
3. 聊天页（同一或新会话）再请求 demo 工具 → 仍提示工具不存在。
4. 绕过缓存的路径（POST /api/chat/stream 不带 agent_id，走全局 AGENT）→ crm_ping 正常。

## 证据（2026-10-16 实测）

对照实验（同一后端进程，admin 登录）：

| 路径 | echo | crm_ping |
|---|---|---|
| 全局 AGENT（热重建会重建） | ✅ `[echo] hi-global` | ✅ `[MCP] pong: hi-global` |
| `AGENT_CACHE["agent:default"]`（UI 聊天恒带 agent_id → 走此路径） | ✅ | ❌ 工具不存在 |

用户浏览器线程 `xa9zl1wcmvamuhjg` 历史：echo 成功、crm_ping 被回复「不存在」，与上表一致。

## 根因

`main.py` 的 `PUT /api/admin/agents/{agent_id}`、`POST /api/admin/agents/{agent_id}/set-default`、
`DELETE /api/admin/agents/{agent_id}` 三处热重建只重建全局 `AGENT`，
从不清理 `AGENT_CACHE[f"agent:{agent_id}"]`。

前端 `ChatView.vue` 聊天请求恒带 `agent_id`，`get_agent_for()` 命中陈旧缓存条目，
后台任何「保存并热重建」对聊天页都不生效。
