# MCP 使用指南（AgentServer）

> 适用版本：当前 `main` 分支（含 MCP 工具接入、身份注入/越界闸、后台可视化管理与聊天页 Agent 选择）。
> 相关代码：`backend/agent/mcp_tools.py`、`backend/main.py`；前端 `src/components/McpServers.vue`、`src/views/{ToolsView,AgentEditView,ChatView}.vue`。

---

## 1. 概述

MCP（Model Context Protocol）让 Agent 在不改业务代码的前提下，挂载**外部工具服务器**，把其暴露的工具并入当前 Agent 的工具集。

- **配置粒度**：MCP 服务器以 `mcp_servers` 数组存放在**每个 Agent 的配置**里（SQLite `agent_config` 表），因此**逐 Agent 独立**。
- **传输方式**：`stdio` / `sse` / `streamable_http`。
- **身份与安全**：每个服务器可配 `allow_roles` 越权闸；调用时按**当前登录用户角色**拦截，越权工具不会真正执行，直接返回"⛔ 无权限"。
- **热重建**：在后台保存即生效，无需重启服务。

测试用的 MCP 服务器示例：`backend/tests/mcp_demo_server.py`，暴露 `crm_ping`（回显）与 `add`（求和）两个工具。

---

## 2. 配置格式

每个 Agent 配置含 `mcp_servers` 字段，元素结构如下：

```jsonc
{
  "name": "demo",                 // 唯一标识
  "transport": "stdio",           // stdio | sse | streamable_http
  "enabled": true,                // 是否启用（默认 true）
  "allow_roles": ["admin"],       // 可选：允许调用的角色；缺省=不限制
  // stdio 专用：
  "command": "/path/venv/bin/python",
  "args": ["tests/mcp_demo_server.py"],
  "env": { "API_KEY": "xxx" },    // 可选
  // sse / streamable_http 专用：
  "url": "http://host:8001/mcp",
  "headers": { "Authorization": "Bearer <token>" }  // 可选
}
```

三种传输对照：

| transport | 必填 | 说明 |
| --- | --- | --- |
| `stdio` | `command` + `args` | 拉起本地子进程（如 Python MCP server） |
| `sse` | `url` | Server-Sent Events 端点 |
| `streamable_http` | `url` | Streamable HTTP 端点 |

`allow_roles` 缺省或不填 = 不限制（保持原行为）；填 `["admin"]` 表示仅管理员可调，普通用户调用被拒。

---

## 3. 身份注入与越权闸

实现位于 `backend/agent/mcp_tools.py`：

- 每次对话开始时，`main.py` 的 `chat_stream` 调用 `set_user_ctx(user_id, role)`，把当前用户身份写入 `ContextVar`（按请求任务隔离）。
- `load_mcp_tools(servers, apply_policy=True)` 在加载每个 MCP 服务器后，用 `_wrap_tool` 把其每个工具包一层**异步闸**：
  - 越权（`role not in allow_roles`）→ 直接返回 `⛔ 无权限：MCP 服务器「<name>」的工具仅允许角色 [...] 调用，当前角色为 <role>。`，**工具不会真正执行**。
  - 放行 → `ainvoke` 委托原工具。
- 预览接口 `/api/admin/mcp/discover` 走 `apply_policy=False`，仅列举工具、不做角色限制（方便后台测试连接）。

> 说明：当前身份透传到 MCP 服务器的是**静态配置**（如 `headers`、`env`）；按请求用户动态注入身份头受限于 `langchain-mcp-adapters` 会话模型，可作为后续增强。真正鉴权仍由对应 MCP 服务端负责（HTTP 用 `headers`、stdio 用进程/环境变量）。

---

## 4. 后台管理 UI

### 4.1 工具列表页（多 Agent 切换）
路径：后台 → **工具**。MCP 区块顶部有 **「选择 Agent」** 下拉（列出全部 Agent，默认 Agent 标注「（默认）」）。

- 切到某 Agent 即加载其 `mcp_servers`；
- **+ 新增服务器**：填名称、选传输方式、按类型填命令/参数或 URL/请求头，可设 `allow_roles` 与启用开关；
- 每个服务器支持 **测试连接**（调 discover 预览暴露的工具）、**编辑**、**删除**；
- **保存并热重建**：写入所选 Agent 的 `mcp_servers` 并 PUT（后端热重建）。

### 4.2 Agent 编辑页（逐 Agent）
路径：后台 → **Agent 列表** → 任意 Agent「编辑」。底部有独立 **「MCP 服务器」** 区块，管理与 4.1 同一套 `McpServers` 组件，绑定**当前 Agent**。

> 两处编辑的是同一份数据：工具页按 Agent 切换、Agent 编辑页内联当前 Agent，互不冲突。

### 4.3 聊天页（选择 Agent）
路径：聊天页顶部 **Agent 下拉**。选择非默认 Agent 后即可在对话里用到它挂载的 MCP 工具；切换 Agent 自动开新会话，避免不同 Agent 上下文混用。
- 任意已登录用户（含普通用户）都能看到并选择 Agent；工具仍受各自 `allow_roles` 越权闸约束。

---

## 5. 添加并验证一个 MCP 服务器

以 `stdio` + 内置 demo server 为例：

1. 后台 → **工具** → 顶部选「默认 DeepAgent」→ **+ 新增服务器**：
   - 名称：`demo`
   - 传输：`stdio`
   - 启动命令：`<backend>/venv/bin/python`
   - 参数：`tests/mcp_demo_server.py`
   - 点 **测试连接** → 提示「暴露 2 个工具」；
   - 点 **确定** → **保存并热重建**。
2. 聊天页以**管理员**身份说「调用 crm_ping，传 hello」→ 返回 `[MCP] pong: hello`。
3. 若把该服务器 `allow_roles` 设为 `["admin"]`，**普通用户**同样一句话会收到 `⛔ 无权限…当前角色为 user。`
4. 回到工具页删除该服务器并保存 → 工具不再可用。

命令行等价验证（管理员 token 记为 `$TOKEN`）：

```bash
# 预览工具（含 allow_roles 限制也不影响列举）
curl -s -X POST localhost:8000/api/admin/mcp/discover \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '[{
    "name":"demo","transport":"stdio",
    "command":"/Volumes/Samsung/AI/Project/AgentServer/backend/venv/bin/python",
    "args":["/Volumes/Samsung/AI/Project/AgentServer/backend/tests/mcp_demo_server.py"],
    "allow_roles":["admin"]}]'

# 拉取默认 Agent 并挂服务器（保存即热重建）
AID=$(curl -s localhost:8000/api/admin/agents -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;print([a['id'] for a in json.load(sys.stdin)['agents'] if a['is_default']][0])")
curl -s localhost:8000/api/admin/agents/$AID -H "Authorization: Bearer $TOKEN" > /tmp/a.json
python3 -c "import json;d=json.load(open('/tmp/a.json'))['agent'];d['mcp_servers']=[{'name':'demo','transport':'stdio','command':'/Volumes/Samsung/AI/Project/AgentServer/backend/venv/bin/python','args':['/Volumes/Samsung/AI/Project/AgentServer/backend/tests/mcp_demo_server.py'],'allow_roles':['admin']}];json.dump(d,open('/tmp/a2.json','w'))"
curl -s -X PUT localhost:8000/api/admin/agents/$AID -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d @/tmp/a2.json
```

---

## 6. 更完整的 MCP 测试服务（多能力覆盖）

`backend/tests/mcp_demo_server.py` 仅暴露 `crm_ping` / `add` 两个工具，适合最小连通性验证。
若要**全面验证 agent 的 MCP 集成能力**（多种参数/返回类型、异步、结构化入参、错误恢复等），
使用 `backend/tests/mcp_test_server.py`，它刻意覆盖更丰富的工具形态：

| 工具 | 覆盖的能力维度 |
| --- | --- |
| `echo` | 最简单调用链路与参数传递 |
| `add` / `multiply` | 多参数 + int / float 类型 |
| `get_server_uptime` | 无参工具 |
| `concat` / `search_items` | `list` 参数 + 带默认值参数 |
| `summarize_record` | 结构化 `dict` 对象入参（考验结构化参数抽取） |
| `is_even` / `reverse_text` | bool 返回值 / 字符串处理 |
| `fetch_quote` | **异步**工具（asyncio 调用链路） |
| `always_fail` | 故意失败，验证 agent 错误恢复 |

### 6.1 三种传输验证

同一份代码可分别以 `stdio` / `sse` / `streamable_http` 暴露，由环境变量 `MCP_TRANSPORT` 切换（默认 stdio）：

```bash
# stdio（由 agent 以子进程拉起，无需手动启动）
<backend>/venv/bin/python tests/mcp_test_server.py

# sse：URL = http://MCP_HOST:MCP_PORT/sse
MCP_TRANSPORT=sse MCP_PORT=8001 <backend>/venv/bin/python tests/mcp_test_server.py

# streamable_http：URL = http://MCP_HOST:MCP_PORT/mcp
MCP_TRANSPORT=streamable_http <backend>/venv/bin/python tests/mcp_test_server.py
```

stdio 接入配置（其余字段同 §2，把 `args` 指向本文件即可）：

```jsonc
{ "name": "test-suite", "transport": "stdio", "enabled": true,
  "command": "<backend>/venv/bin/python", "args": ["tests/mcp_test_server.py"] }
```

### 6.2 自动化测试

- `tests/test_mcp_test_server.py`：冒烟测试，静态加载模块校验 11 个工具全部注册（无需网络）。
- `tests/test_mcp_gate.py`：**集成测试**，真实拉起 `mcp_test_server` 子进程并挂 `allow_roles=["admin"]`，
  分别以 `user` / `admin` 角色调用 `echo`，断言越权被闸拦截（`⛔ 无权限`）、授权正常执行。

```bash
cd backend && ./venv/bin/python -m pytest tests/test_mcp_test_server.py tests/test_mcp_gate.py -q
```

## 7. 安全与边界

- **越权闸是前置于工具执行的拦截**，与 CRM 工具的 `allow_roles` 机制一致；它不替代 MCP 服务端自身的鉴权。
- `allow_roles` 按**服务器**粒度设置，可对不同外部工具服务器施加不同角色策略。
- 聊天页 Agent 列表 `/api/agents` 对**任意已登录用户**可见（仅摘要 `id/name/is_default`），不暴露配置细节；具体工具的越权仍由闸控制。
- 单个 MCP 服务器连接失败**不影响其余服务器**的加载（逐服务器建连）。
