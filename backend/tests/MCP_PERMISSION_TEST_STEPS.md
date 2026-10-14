# MCP 角色权限闸 · 测试步骤记录（落盘）

> 本文档为 MCP 权限控制（调用前角色闸）的**示例 + 测试步骤 + 执行记录**，
> 与 `tests/test_mcp_permission_demo.py` 配套。评审/执行后请在「七、实际执行记录」填写结果。

---

## 一、示例概述

把 `tests/mcp_test_server.py`（内置 `echo` 工具，正常返回 `[echo] <文本>`）当作一个
**敏感 MCP 服务器**。在服务器描述里加 `allow_roles`，即声明「只有名单内的角色能调用本服务器全部工具」。

本示例配置（等价于在后台「Agent 编辑 → MCP 服务器」里填的内容）：

```json
{
  "name": "test-suite",
  "transport": "stdio",
  "enabled": true,
  "command": "python",
  "args": ["tests/mcp_test_server.py"],
  "allow_roles": ["admin"]
}
```

权限规则（`agent/mcp_tools.py` 的 `_guarded`）：
- `allow_roles` 为空 → 所有登录用户可用；
- `allow_roles=["admin"]` → 仅 `role == "admin"` 放行，其余返回 `⛔ 无权限`，**工具不执行**；
- 当前用户 `role` 来自 JWT，经 `/api/chat/stream` 的 `set_user_ctx(id, role)` 写入 `ContextVar`。

---

## 二、被测对象

| 项 | 值 |
|---|---|
| 被测函数 | `agent.mcp_tools._guarded`（`_wrap_tool` 包装后的工具） |
| 触发入口 | `load_mcp_tools(servers, apply_policy=True)` → 工具被调用 |
| 工具 | `echo`（参数 `text: str`，返回 `[echo] <text>`） |
| 判定依据 | `user_ctx_var` 中的 `role` 字符串是否在 `allow_roles` |
| 非目标 | 外部 MCP 服务器自身鉴权（本例不覆盖，属服务端职责） |

---

## 三、5 条测试数据

| # | 用户ID | 姓名 | role | 预期 expect | 说明 |
|---|---|---|---|---|---|
| 1 | u-admin-1001 | 张管理员 | `admin` | **allow** | 管理员，命中白名单 |
| 2 | u-admin-1002 | 李主管 | `admin` | **allow** | 另一名管理员，命中白名单 |
| 3 | u-user-2001 | 王普通用户 | `user` | **deny** | 普通用户，不在名单 |
| 4 | （无） | 匿名请求 | `None` | **deny** | 未鉴权，上下文为空 |
| 5 | u-custom-3001 | 赵审计 | `auditor` | **deny** | 自定义角色（非 admin），一律拒绝 |

> 数据即「身份样例」。生产中这些对应真实用户：admin 账号 `role=admin`，普通/自定义角色用户
> 的 JWT `role` 归一为 `user`（见 `agent/auth.py` 的 `create_user`），因此同样被拒。

---

## 四、自动化测试（推荐）

**文件**：`backend/tests/test_mcp_permission_demo.py`
**数据**：见第三节 `CASES`（2 allow / 3 deny）
**命令**：

```bash
cd backend
./venv/bin/python -m pytest tests/test_mcp_permission_demo.py -v
```

**断言**：
- `expect == "allow"` → 返回必须严格等于 `"[echo] hi"`；
- `expect == "deny"` → 返回必须包含 `"⛔ 无权限"`。

**预期输出**（示意，pytest 应全绿）：

```
tests/test_mcp_permission_demo.py::test_mcp_role_gate[张管理员] PASSED
tests/test_mcp_permission_demo.py::test_mcp_role_gate[李主管]   PASSED
tests/test_mcp_permission_demo.py::test_mcp_role_gate[王普通用户] PASSED
tests/test_mcp_permission_demo.py::test_mcp_role_gate[匿名请求]   PASSED
tests/test_mcp_permission_demo.py::test_mcp_role_gate[赵审计]     PASSED
```

---

## 五、手动验证步骤（不依赖 pytest）

适用于想在真实服务上复现。需先启动后端，并让某 Agent 的 `mcp_servers` 带上 `allow_roles=["admin"]`。

1. **取管理员令牌**
   ```bash
   curl -s -X POST http://localhost:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"admin123"}' | tee /tmp/admin.json
   ADMIN_TOKEN=$(python -c "import json;print(json.load(open('/tmp/admin.json'))['token'])")
   ```
2. **取普通用户令牌**：先创建普通用户（或用一个已知 user 角色账号），同样 `/api/auth/login` 取 `USER_TOKEN`。
3. **以管理员身份发消息触发 MCP 工具** → 期望工具正常执行、返回真实结果。
4. **以普通用户身份发同一消息** → 期望 Agent 拿到 `⛔ 无权限`，工具未执行。

> 也可用一段独立脚本直接验证闸（无需后端 HTTP）：
> ```bash
> cd backend && ./venv/bin/python - <<'PY'
> import asyncio, sys
> sys.path.insert(0, 'tests')
> from agent.mcp_tools import load_mcp_tools, set_user_ctx
> async def main():
>     srv=[{"name":"t","transport":"stdio","enabled":True,
>           "command":"python","args":["tests/mcp_test_server.py"],"allow_roles":["admin"]}]
>     tools,_=await load_mcp_tools(srv, apply_policy=True)
>     echo=next(t for t in tools if t.name=="echo")
>     for role in ("admin","user"):
>         set_user_ctx("u", role)
>         print(role, "->", await echo.ainvoke({"text":"hi"}))
> asyncio.run(main())
> PY
> ```
> 预期：`admin -> [echo] hi`；`user -> ⛔ 无权限：...`

---

## 六、预期结果对照表

| # | 姓名 | role | 调用结果（预期） |
|---|---|---|---|
| 1 | 张管理员 | admin | `[echo] hi` |
| 2 | 李主管 | admin | `[echo] hi` |
| 3 | 王普通用户 | user | `⛔ 无权限：MCP 服务器「test-suite」的工具仅允许角色 ['admin'] 调用，当前角色为 user。` |
| 4 | 匿名请求 | None | `⛔ 无权限：...当前角色为 None。` |
| 5 | 赵审计 | auditor | `⛔ 无权限：...当前角色为 auditor。` |

---

## 七、实际执行记录（评审/执行后填写）

| # | 姓名 | role | 实际返回 | 是否一致 | 执行人 / 日期 |
|---|---|---|---|---|---|
| 1 | 张管理员 | admin |  | □ |  |
| 2 | 李主管 | admin |  | □ |  |
| 3 | 王普通用户 | user |  | □ |  |
| 4 | 匿名请求 | None |  | □ |  |
| 5 | 赵审计 | auditor |  | □ |  |

自动化测试结论：□ 全绿  □ 有失败（附日志）

---

## 八、备注

- 本示例只验证**调用前闸**；真实数据权限仍由外部 MCP 服务器兜底（如 HTTP/SSE 的 `headers` 令牌）。
- 当前 `allow_roles` 仅能取 `["admin"]` 或空：自定义角色在 `create_user` 被归一为 `user`，
  网关尚未细化到「自定义角色级 ACL」（如需，改 `_guarded` 比对 `roles.key`/`role_id`）。
- 后台「测试连接/预览工具」接口用 `apply_policy=False`，**不套闸**，仅列举，与本测试无关。
