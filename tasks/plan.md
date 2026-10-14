# Plan: 大规模知识库 RAG 子系统

> 关联：`SPEC.md`（已评审）。按能力地图构建顺序执行，每个任务改动文件 ≤ 5 个。

## 构建顺序与依赖
```
kb-store ──▶ kb-retrieval ──▶ kb-ingestion ──▶ kb-tool ──▶ kb-api ──▶ kb-ui
```
- `kb-store`：Qdrant 客户端 + 每 KB 一个 collection（dense + sparse 双向量）
- `kb-retrieval`：dense + BM25 稀疏混合检索 + RRF 融合，封装 langchain Retriever
- `kb-ingestion`：文档加载 → 切分 → 去重(hash) → 双向量入库；含 CLI
- `kb-tool`：`search_knowledge_base` @tool，挂入现有 `deep_agent`
- `kb-api`：FastAPI 路由（创建/列出/删除 KB、上传文档、检索），挂载到 `main.py`
- `kb-ui`：Vue 管理界面（列表/创建/删除/上传/检索测试）

## 关键技术决策
- 双向量：dense（`EMBEDDING_*` OpenAI 兼容）+ sparse（`fastembed` `Qdrant/bm25`），Qdrant 原生 sparse 向量。
- 融合：RRF（k=60），不引入额外依赖。
- 隔离：collection 命名 `kb_{kb_id}`，`kb_id` 正则校验 `^[A-Za-z0-9_-]{1,64}$`。
- 优雅降级：`EMBEDDING_API_KEY` 缺失时，入库/检索返回明确提示，不崩溃。
- 单文件 ≤ 10MB 校验（`MAX_FILE_BYTES`）。

## 风险与缓解
- Qdrant 未启动 → 启动检测，API 返回 503 + 提示 `docker run qdrant`。
- fastembed BM25 中文效果有限 → 预留 `SPARSE_MODEL` 环境变量，后续可换 `Qdrant/bm25-zh`。
- Embedding 密钥缺失阻塞 dense → 已做降级，密钥就位即生效。

## 验证检查点
- 每模块单测（`:memory:` Qdrant）通过。
- 后端起服后 `curl` 跑通 创建→上传→检索 闭环。
- agent 提 KB 相关问题能自动调用 `search_knowledge_base`。
- 前端页面可完成 列表/创建/删除/上传/检索。
