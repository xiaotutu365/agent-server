# bug: 模型配置的嵌入 dim 不生效（与 KB 配置漂移）

## 现象

后台「模型配置」新增嵌入模型时填写的「向量维度 dim」实际不参与运行：

- `kb/embed.py::_ensure_dense()` 用模型配置条目只覆盖 `base_url / model / api_key`，
  `dimensions` 仍取 KB 配置的 `embedding_dim`（默认 1536）
- Qdrant 建集合的向量 size 同样只读 `settings["embedding_dim"]`
  （`kb/store.py::_vectors_config`、`memory/vector.py::ensure_collection`）

后果：模型配置填 dim=2048（如智谱 embedding-3）但 KB 配置 embedding_dim=1536 时，
实际请求发 `dimensions=1536`、集合按 1536 建——表单 dim 沦为仅校验/展示字段，
两处配置易漂移不一致且用户无从察觉。

附带问题：模型配置 create/update/delete 端点只清 `AGENT_CACHE`，不调
`kb.embed.reset_clients()`，嵌入客户端实例被缓存，改完配置不重启进程不生效
（与 MCP 配置热重建后 AGENT_CACHE 未失效同类问题，见 project_memory）。

## 复现步骤

1. 「模型配置」添加嵌入模型：dim=1024，设为默认
2. 「知识库配置」保持 embedding_dim=1536（默认）
3. 新建知识库并上传文档 → 观察实际请求 dimensions 与集合 size 均为 1536

## 期望

模型配置成为嵌入模型+维度的单一事实来源：默认嵌入条目 dim>0 时，
`OpenAIEmbeddings.dimensions` 与新建集合 size 均取该 dim；无条目时回退 KB 配置（兼容现状）。

## 证据

- backend/kb/embed.py L34-59（覆盖三字段、未覆盖 dim）
- backend/kb/store.py L38-40、backend/memory/vector.py L28-33（size 取 settings）
- backend/main.py L708-737（模型端点无 reset_clients）
