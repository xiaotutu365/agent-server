# Spec: 大规模知识库 RAG 子系统（AgentServer）

> 状态：待评审（Phase 1 / Specify）。评审通过后再进入 Phase 2 计划与 Phase 3 任务拆解。
> 技能：spec-driven-development。能力地图模块 id：`kb-store` / `kb-retrieval` / `kb-ingestion` / `kb-tool` / `kb-api`。

---

## 能力地图（Capability Map，Phase 0 已确认方向）

| Module id | 职责 | 依赖 | 默认选型 |
|---|---|---|---|
| `kb-store` | Qdrant 连接、集合管理、多知识库隔离 | — | 每知识库一个 collection：`kb_{kb_id}` |
| `kb-retrieval` | dense + BM25 稀疏混合检索，RRF 融合，封装为 langchain Retriever | `kb-store` | langchain-qdrant + fastembed(BM25) |
| `kb-ingestion` | 文档加载、切分、去重、Embedding 入库（CLI + 函数） | `kb-store` | langchain-community loaders |
| `kb-tool` | 把检索封装成 `@tool` 挂入现有 `deep_agent` | `kb-retrieval` | langchain_core.tools.tool |
| `kb-api` | 知识库管理 API（创建/删除/列出/上传/检索） | `kb-ingestion`, `kb-store` | FastAPI router |
| `kb-ui` | 前端：前台对话页（agent 自动用 KB）+ 后台知识库管理页（创建/删除/上传） | `kb-api` | Vue 3 + Vite（现有前端，vue-router 拆分前后台） |

构建顺序：`kb-store` → `kb-retrieval` → `kb-ingestion` → `kb-tool` → `kb-api` → `kb-ui`

---

## Objective（目标）

给现有 AgentServer（deepagents + LangChain/LangGraph + SQLite 会话持久化）**新增大规模、多租户的知识库检索能力**，替换此前"sqlite-vec 小库"方案——sqlite 单文件写锁、无水平扩展、无量化压缩，无法支撑大知识库。

用户故事：
1. 运维/业务方可通过 API **创建知识库**、**上传文档**（md/txt/pdf/docx），系统自动切分并向量化入库。
2. 终端用户向 deep agent 提问时，当问题命中某知识库主题，agent 自动调用 `search_knowledge_base` 工具获取相关片段作答。
3. 多个知识库之间**硬隔离**（按 collection 划分），一个 KB 的文档不会泄漏到另一个 KB 的检索结果。
4. 检索采用 **dense 向量 + BM25 稀疏混合 + RRF 融合**，在大库、专有名词/编号类查询上召回优于纯向量。

成功样貌：一个可独立扩展的向量服务（Qdrant）+ 一套与现有 agent 工具链同构的检索工具，agent 主体与 SQLite 会话逻辑不变。

---

## Tech Stack（技术栈）

| 类别 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.13 | 现有 |
| Web 框架 | FastAPI（现有 `backend/main.py`） | 新增 router |
| Agent | deepagents + LangChain + LangGraph（现有） | `deep_agent.py:67` `create_deep_agent` |
| 向量库 | **Qdrant**（Rust，Docker 部署） | 默认 `localhost:6333`，远程走 `QDRANT_URL`/`QDRANT_API_KEY` |
| Dense Embedding | **OpenAI 兼容 API**（`text-embedding-3-small`） | `langchain_openai.OpenAIEmbeddings`，`EMBEDDING_*` 环境变量 |
| Sparse Embedding (BM25) | `fastembed` `SparseTextEmbedding("Qdrant/bm25")` | 仅本地 CPU，无需外部服务 |
| 检索融合 | RRF（Reciprocal Rank Fusion） | 自实现，无额外依赖 |
| 文档加载 | `langchain-community` document_loaders + `pypdf` + `python-docx` | 新增依赖 |
| langchain 集成 | `langchain-qdrant` | 新增依赖 |
| 前端 | Vue 3 + Vite（现有 `frontend/`） | 新增 `kb` 页面与 API 调用 |

**新增 pip 依赖（写入 `backend/requirements.txt`，走清华源安装）：**
```
qdrant-client>=1.13
langchain-qdrant>=0.2
fastembed>=0.3
langchain-community>=0.3
pypdf>=5
python-docx>=1.1
```
> 注：DeepSeek **无** embedding 接口，故 Embedding 走独立 `EMBEDDING_*` 配置，与现有 `OPENAI_*` 聊天配置解耦。
> 注：`EMBEDDING_API_KEY` 暂未提供，代码须**优雅降级**——入库/检索时若密钥缺失，返回明确提示而非崩溃；密钥就位后无需改代码即可工作。

---

## Commands（命令）

```bash
# 1. 启动 Qdrant（本地 Docker，一次性）
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 2. 安装新增依赖（项目根在 backend/，venv 已建）
cd /Volumes/Samsung/AI/Project/AgentServer/backend
./venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 启动后端（含 KB API 与 agent）
./venv/bin/python main.py

# 4. 知识库入库（CLI 示例）
./venv/bin/python -m kb.ingest --kb_id policy --path ./docs --recursive

# 5. 运行测试
./venv/bin/python -m pytest tests/ -q

# 6. 前端（不变）
cd /Volumes/Samsung/AI/Project/AgentServer/frontend && npm run dev
```

环境变量（加入 `backend/.env`）：
```
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
EMBEDDING_API_KEY=sk-...
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

---

## Project Structure（项目结构）

```
backend/
  kb/
    __init__.py
    config.py       # 读取 QDRANT_*/EMBEDDING_* 环境变量，常量
    store.py        # Qdrant 客户端、create/drop/list collection、kb_id 校验
    embed.py        # DenseEmbedder(OpenAI) + SparseEmbedder(BM25) 封装
    ingest.py       # load → split → dedup(hash) → upsert；CLI 入口
    retrieval.py    # hybrid_search(kb_id, query, top_k) + RRF；langchain Retriever 适配
    tools.py        # search_knowledge_base @tool；导出 KB_TOOLS
    api.py          # FastAPI router：POST /kb, DELETE /kb/{id}, GET /kb,
                    #   POST /kb/{id}/documents, POST /kb/{id}/search
  main.py           # 挂载 kb.api.router；在 tools 中增加 *KB_TOOLS
  tests/
    test_kb_store.py        # 集合创建/隔离/删除（用 :memory: Qdrant）
    test_kb_embed.py        # dense/sparse 维度与异常
    test_kb_ingest.py       # 切分/去重逻辑（mock embedding）
    test_kb_retrieval.py    # hybrid + RRF + kb_id 过滤（:memory:）
```

```
frontend/
  src/
    views/ChatView.vue        # 前台：用户对话页（agent 自动调用 search_knowledge_base 使用知识库）
    views/KbAdmin.vue         # 后台：知识库管理（列表/创建/删除/上传），独立页面，不与前台混排
    api/kb.js                 # 封装 /kb/* 请求（走 vite 代理到 :8000）
  vite.config.js              # 已有代理 localhost:8000（vite.config.js:10）
```

> 设计约束：每个任务改动文件 ≤ 5 个；`kb/` 模块不依赖前端；`store.py` 通过 `:memory:` 模式支持单测。

---

## Code Style（代码风格）

沿用现有 `backend/tools/*.py` 风格：中文 docstring、类型标注、`os.getenv` 读配置、工具用 `@tool` 装饰器并返回 `str`。

```python
"""知识库检索工具：封装 Qdrant 混合检索为 deep agent 可用工具。"""

from langchain_core.tools import tool


@tool
def search_knowledge_base(query: str, kb_id: str = "default", top_k: int = 5) -> str:
    """从指定知识库检索与问题相关的文档片段。

    当用户问到内部制度、产品文档、FAQ、历史资料等不在联网范围的知识时调用。
    示例: search_knowledge_base("退货政策", kb_id="policy")
    """
    from kb.retrieval import hybrid_search

    docs = hybrid_search(kb_id=kb_id, query=query, top_k=top_k)
    if not docs:
        return "未在该知识库中找到相关内容。"
    return "\n\n".join(
        f"[来源: {d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs
    )


KB_TOOLS = [search_knowledge_base]
```

约定：
- 模块内函数/变量 `snake_case`，类名 `CapWords`。
- 所有对外部服务（Qdrant/Embedding）的调用包 `try/except`，返回可读错误字符串而非抛栈。
- `kb_id` 仅允许 `[a-zA-Z0-9_-]`，长度 1–64，非法直接拒绝（防注入/越权跨库）。

---

## Testing Strategy（测试策略）

- 框架：**pytest**（新增）。Qdrant 用 `QdrantClient(":memory:")` 做单测，避免依赖外部服务。
- 位置：`backend/tests/`，按模块 `test_kb_*.py`。
- 层级：
  - **单元**：切分/去重（mock embedding）、RRF 融合排序、kb_id 校验、store 集合隔离（:memory:）。
  - **集成（可选，标 `@pytest.mark.integration`）**：连本地 Docker Qdrant 跑真实 ingest→retrieve 闭环。
- 覆盖目标：核心模块（`store`/`retrieval`/`ingest`）行覆盖 ≥ 70%。
- RAG 质量不靠单测断言，靠**冒烟用例**： ingested 的文档内容能在同 kb 检索命中、且**不会**在另一 kb 命中（隔离验证）。
- 提交前必须 `pytest` 通过（见 Boundaries）。

---

## Boundaries（边界）

**Always（始终做）**
- 提交前运行 `pytest` 并保证通过。
- 通过 langchain `Retriever` 抽象访问向量库，保持可替换（将来换 Milvus 不改 agent）。
- 知识库严格按 collection 隔离，检索始终带 `kb_id` 过滤。
- 校验所有外部输入（`kb_id` 格式、文件类型、chunk 上限）。
- 单文件大小 ≤ **10MB**（覆盖"几 MB 到 10MB"需求），超限拒绝并返回提示。
- Embedding/检索失败返回可读错误，不向上抛栈中断 agent。

**Ask first（先确认）**
- 修改 agent `SYSTEM_PROMPT` 中关于知识库的措辞。
- 新增 pip 依赖或升级现有依赖版本。
- 变更 Qdrant collection 命名规则或 payload schema。
- 新增/修改对外 API 路由或请求体结构。
- 调整 Embedding 模型（影响已入库向量，需重建）。

**Never（绝不做）**
- 提交 `.env` 或任何密钥/API Key。
- 编辑 `venv/`、`node_modules/` 等 vendor 目录。
- 未经确认删除 Qdrant 中知识库数据。
- 绕过知识库隔离（导致跨 kb 数据泄漏）。
- 在无审批情况下删除或跳过失败测试。

---

## Success Criteria（成功标准，可验证）

1. **管理 API**：`POST /kb` 创建、`DELETE /kb/{id}` 删除、`GET /kb` 列出，均返回预期状态码与结构。
2. **入库**：上传 md/txt/pdf/docx 后，文档被切分并写入对应 `kb_{kb_id}` collection，文档数可查。
3. **隔离**：`search_knowledge_base(kb_id="A")` 不会返回仅入库到 `B` 的文档内容。
4. **混合检索**：对专有名词/编号类查询，hybrid 召回 ≥ dense-only 召回（冒烟用例验证）。
5. **Agent 集成**：向 agent 提 KB 相关问题时，自动调用 `search_knowledge_base` 并引用来源作答。
6. **可扩展**：单 collection 可承载 ≥ 10 万向量；检索 P95 延迟 < 200ms（本地 Docker，中等硬件）。
7. **测试**：`pytest` 全绿，核心模块覆盖 ≥ 70%。
8. **前端**：
   - 前台对话页：用户提问时 agent 自动从知识库检索引用（无需用户手动选 KB）。
   - 后台管理页：可列出/创建/删除知识库、上传文档（≤10MB）、检索测试，结果与 API 一致。
   - 两者为独立路由页面（`/` 前台、`/admin/kb` 后台），后台不与前台对话混排。

---

## Open Questions（已确认）

1. **Qdrant 部署形态**：✅ 本地 Docker（`localhost:6333`），`QDRANT_URL` 仍预留以备后续远程。
2. **前端 KB 管理 UI**：✅ 本期一并实现（Vue 管理界面，`kb-ui` 模块）。
3. **Embedding 密钥**：⏳ 暂未提供，代码先写并**优雅降级**（缺密钥时明确提示，就位即用，无需改动）。
4. **文档与规模上限**：✅ 单文件 **≤ 10MB**（几 MB 到 10MB）；单 KB 文档数、单文档 chunk 数暂不限制。
5. **隔离粒度**：✅ 采用"每 KB 一个 collection"（硬隔离、易删、易扩展）。
