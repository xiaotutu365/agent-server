# MCP 页面功能测试流程(UI 手动验证)

> 适用:在浏览器页面上手动验证 MCP 接入、聊天调用与越权闸。
> 关联文档:[MCP_GUIDE.md](MCP_GUIDE.md)(配置格式与原理)、[MCP_PERMISSION_TEST_STEPS.md](../backend/tests/MCP_PERMISSION_TEST_STEPS.md)(权限闸自动化测试)。
> 本流程已在 2026-10-16 全链路验证通过(见文末「已知实测结果」)。

---

## 一、前置条件

| 项 | 值 | 检查方式 |
|---|---|---|
| 后端服务 | `http://localhost:8000` | 浏览器打开 `http://localhost:8000/docs` 能出 Swagger |
| 前端服务 | `http://localhost:5173` | Vite dev,`/api` 已代理到 8000 |
| 管理员账号 | `admin` / `admin123` | 登录页可进 |
| 普通用户账号 | 需先创建(见场景 C 第 1 步) | 用于越权闸测试 |

启动命令(Windows,如服务未运行):

```powershell
# 后端:cwd 必须是 backend 目录(当前配置用了相对路径)
cd e:\EdaProjects\github\AgentServer\backend
.\venv\Scripts\python.exe main.py

# 前端
cd e:\EdaProjects\github\AgentServer\frontend
npm run dev
```

## 二、当前测试数据(默认 Agent「默认 DeepAgent」已挂载)

| 服务器名 | 传输 | 工具 | 正常返回示例 |
|---|---|---|---|
| `test-suite` | stdio | 11 个:`echo`/`add`/`multiply`/`get_server_uptime`/`concat`/`search_items`/`summarize_record`/`is_even`/`reverse_text`/`fetch_quote`/`always_fail` | `echo(text="hello")` → `[echo] hello` |
| `demo` | stdio | 2 个:`crm_ping`/`add` | `crm_ping(message="hello")` → `[MCP] pong: hello` |

两个服务器当前均**未设置** `allow_roles`(不限制角色)。

---

## 三、测试场景

### 场景 A:后台「MCP 服务器」页 — 测试连接 / 预览工具

1. 以 admin 登录 `http://localhost:5173/#/login`。
2. 进入后台 → 左侧菜单 **「MCP 服务器」**(`/#/admin/mcp`)。
3. 顶部 **「选择 Agent」** 选「默认 DeepAgent」→ 列表应显示 `test-suite` 与 `demo` 两台服务器。
4. 点 `test-suite` 的 **「测试连接」** → 预期:提示暴露 **11 个工具**。
5. 点 `demo` 的 **「测试连接」** → 预期:提示暴露 **2 个工具**。

> 注意:「测试连接」只列举工具、**不套角色闸**,即使配了 `allow_roles` 也总能预览成功,属正常现象。

### 场景 B:聊天页 — admin 正常调用 MCP 工具

1. 回到前台聊天页 `http://localhost:5173/#/`,顶部 **Agent:** 下拉选「默认 DeepAgent」。
2. 发送:`请直接调用 MCP 工具 echo,参数 text 为 hello-mcp,并把工具返回结果原样告诉我。`
3. 预期:回复流中出现 **echo 工具卡片**(可展开看输入/输出),输出为 `[echo] hello-mcp`;最终回复引用该结果。
4. 再发送:`请直接调用 MCP 工具 crm_ping,参数 message 为 hello,并把结果原样告诉我。`
5. 预期:输出 `[MCP] pong: hello`。

### 场景 C:越权闸 — 普通用户被拦截、admin 放行

1. **建普通用户**:后台 → 「用户」页,新建用户(如 `mcp_test_user`,角色选普通用户,记下密码)。
2. **配闸**:后台 → 「MCP 服务器」→ 选默认 Agent → 编辑 `test-suite` → `allow_roles` 填 `admin` → 保存 → 点 **「保存并热重建」** → 预期提示「已保存并热重建 ✓」(无需重启服务)。
3. **普通用户调用**:新开无痕窗口,以 `mcp_test_user` 登录聊天页,发送与场景 B 相同的 echo 消息。
   - 预期:工具卡片输出为 `⛔ 无权限:MCP 服务器「test-suite」的工具仅允许角色 ['admin'] 调用,当前角色为 user。`,**工具未真正执行**;Agent 会转述无权限。
4. **admin 调用**:admin 窗口发送同一消息。
   - 预期:正常返回 `[echo] hello-mcp`(放行)。
5. **还原**:编辑 `test-suite` 清空 `allow_roles` → 保存并热重建。

### 场景 D:新增服务器 → 生效 → 删除还原

1. 后台 → 「MCP 服务器」→ **「+ 新增服务器」**:
   - 名称:`demo2`;传输:`stdio`
   - 启动命令:`e:\EdaProjects\github\AgentServer\backend\venv\Scripts\python.exe`(建议用绝对路径,原因见「常见坑」)
   - 参数:`e:\EdaProjects\github\AgentServer\backend\tests\mcp_demo_server.py`
2. 弹窗内点 **「测试连接」** → 预期:暴露 2 个工具 → 确定。
3. 点 **「保存并热重建」** → 聊天页发:`调用 MCP 工具 crm_ping,参数 message 为 test` → 预期正常返回。
4. 删除 `demo2` → 保存并热重建 → 聊天页再发同一消息 → 预期:工具不再存在,Agent 无法调用。

### 场景 E(可选):SSE / Streamable HTTP 传输

```powershell
# 新开终端,手动拉起 SSE 版测试服务器
cd e:\EdaProjects\github\AgentServer\backend
$env:MCP_TRANSPORT="sse"; $env:MCP_PORT="8001"; .\venv\Scripts\python.exe tests\mcp_test_server.py
```

新增服务器:传输选 `sse`,URL 填 `http://127.0.0.1:8001/sse` → 测试连接应列出 11 个工具。
`streamable_http` 同理:URL 为 `http://127.0.0.1:8002/mcp`(先以对应环境变量启动)。测完关掉该终端即可。

---

## 四、结果记录表

| # | 场景 | 预期 | 通过 |
|---|---|---|---|
| 1 | A:测试连接 test-suite | 11 个工具 | ☐ |
| 2 | A:测试连接 demo | 2 个工具 | ☐ |
| 3 | B:admin 调 echo | `[echo] hello-mcp` | ☐ |
| 4 | B:admin 调 crm_ping | `[MCP] pong: hello` | ☐ |
| 5 | C:普通用户被闸拦截 | `⛔ 无权限…当前角色为 user。` | ☐ |
| 6 | C:admin 同配置放行 | `[echo] …` | ☐ |
| 7 | D:新增→热重建生效 | 聊天可调到新工具 | ☐ |
| 8 | D:删除→热重建失效 | 工具不再可用 | ☐ |
| 9 | E:SSE 测试连接(可选) | 11 个工具 | ☐ |

## 五、常见坑

1. **相对路径依赖后端 cwd**:当前配置里 `tests/mcp_test_server.py`、`.\venv\Scripts\python.exe` 是相对路径,只有后端从 `backend/` 目录启动才能解析;换目录启动会**静默拉起失败**(单服务器失败不影响其余),表现为聊天里根本没有该工具。页面配置建议一律写绝对路径。
2. **Windows 没有 `venv/bin/python`**:指南里的 macOS 命令(`./venv/bin/python`、`/tmp`、heredoc)在 Windows 不可用,对应路径是 `venv\Scripts\python.exe`。
3. **allow_roles 只认 `admin` / `user`**:自定义角色在建号时被归一为 `user`,所以闸名单里写 `admin` 之外的自定义角色不会命中(见 MCP_PERMISSION_TEST_STEPS.md 第八节)。
4. **「测试连接」不代表闸生效**:预览接口不套闸(`apply_policy=False`),验证闸必须走聊天调用(场景 C)。
5. **改完配置必须点「保存并热重建」**:只编辑不保存不会生效;保存后无需重启服务。
6. **旧版后端的缓存坑(已修,需重启到修复版才生效)**:2026-10-16 前的后端,「保存并热重建」只重建全局 agent,不清聊天页实际使用的 `AGENT_CACHE["agent:{id}"]`(前端恒带 agent_id),表现为后台「测试连接」正常、聊天页却提示工具不存在(如 `crm_ping`)。修复见 [bugs/mcp-agent-cache-stale/fix.md](../bugs/mcp-agent-cache-stale/fix.md);若聊天页工具列表与后台配置不一致,先确认后端已重启到修复版,再点一次「保存并热重建」即可自愈。

## 六、已知实测结果(2026-10-16)

自动化测试 8/8 通过;场景 A–D 端到端实测全部符合预期(admin 登录、discover 列 11 工具、echo/crm_ping 真实执行、`allow_roles=["admin"]` 下 user 被拦 / admin 放行、热重建即时生效)。
