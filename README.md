# AgentServer

面向业务场景的多 Agent 服务平台：基于 [deepagents](https://github.com/your-org/deepagents) + LangChain/LangGraph 构建对话 Agent，支持 **MCP 工具集成**与**大规模知识库 RAG**，配套 Vue 3 前后台管理界面。

## 特性

- **多 Agent**：Agent 配置持久化于 SQLite（`agent_config`），后台可管理、切换、选择对话 Agent。
- **MCP 工具集成**：每个 Agent 可挂载外部 MCP 服务器（`stdio` / `sse` / `streamable_http`），
  将其暴露的工具并入当前 Agent 工具集，无需改业务代码即可扩展能力。
  - 身份安全：每个服务器可配 `allow_roles`，调用时按当前用户角色做越权闸（详见 `docs/MCP_GUIDE.md`）。
- **知识库 RAG**：Qdrant 向量库 + dense(OpenAI 兼容) / sparse(BM25) 混合检索 + RRF 融合；
  每知识库一个 collection 硬隔离（详见 `SPEC.md`）。
- **前后台分离**：前台对话页（Agent 自动调用工具/知识库）、后台管理页（Agent 列表、工具/MCP、知识库）。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI（`backend/main.py`）、deepagents + LangChain + LangGraph、SQLite 会话持久化 |
| Agent | `deep_agent`（`backend/agent/`） |
| 向量库 | Qdrant（Docker，默认 `localhost:6333`） |
| Embedding | OpenAI 兼容 API（缺密钥时优雅降级） |
| 前端 | Vue 3 + Vite（`frontend/`），vite 代理到 `:8000` |

## 目录结构

```
backend/
  main.py            # FastAPI 入口，挂载 agent / MCP / KB 路由
  agent/             # Agent 构建、MCP 工具接入（mcp_tools.py：加载/越权闸）
  kb/                # 知识库 RAG 子系统（store/embed/ingest/retrieval/tools/api）
  tools/             # 内置业务工具（如 CRM）
  tests/             # 测试（含 MCP 测试服务套件，见下）
frontend/            # Vue 3 前后台
docs/
  MCP_GUIDE.md       # MCP 接入与使用指南
  SPEC.md            # 知识库 RAG 子系统 Spec
  project-map.md     # 存量模块地图与数据模型
tasks/               # 按功能的任务计划（plan.md / todo.md）
AGENTS.md            # 本项目 agent 工作流约定
```

## 快速开始

### 后端

```bash
cd backend
python -m venv venv && source venv/bin/activate      # 或使用现有 venv
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env                                  # 按需填写 OPENAI_* / EMBEDDING_* / QDRANT_*
python main.py                                        # 启动，默认 :8000
```

环境变量（写入 `backend/.env`，**切勿提交**）：

```
OPENAI_API_KEY=sk-...        # 聊天模型
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
EMBEDDING_KEY=sk-...     # 缺省时 RAG 优雅降级
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

> 知识库检索依赖 Qdrant：`docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant`

### 前端

```bash
cd frontend
npm install
npm run dev            # vite 代理到后端 :8000
```

## MCP 测试

`backend/tests/` 提供两套 MCP 测试服务，用于验证 agent 集成外部 MCP 工具的能力：

- `mcp_demo_server.py`：最小示例（`crm_ping` / `add`）。
- `mcp_test_server.py`：更完整（11 个工具，覆盖多类型参数、无参、`list`/默认值、结构化 `dict` 入参、
  bool 返回、异步、故意失败），且可由 `MCP_TRANSPORT` 切换 `stdio` / `sse` / `streamable_http`。

接入与越权闸验证见 `docs/MCP_GUIDE.md` §6。配套自动化测试：

```bash
cd backend
python -m pytest tests/test_mcp_test_server.py tests/test_mcp_gate.py -q
```

## 测试

```bash
cd backend && python -m pytest tests/ -q     # 全量（知识库单测用 :memory: Qdrant，无需外部服务）
```

## 文档

- `docs/MCP_GUIDE.md` — MCP 接入、身份越界闸、后台可视化管理与验证步骤
- `docs/SPEC.md` — 知识库 RAG 子系统能力地图与 Spec
- `docs/project-map.md` — 存量模块地图与数据模型
- `AGENTS.md` — 本项目 agent 工作流约定（DEFINE→PLAN→BUILD→VERIFY→REVIEW→SHIP）
