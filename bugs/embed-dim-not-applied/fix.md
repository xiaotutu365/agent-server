# 修复记录：embed-dim-not-applied

## 根因

「模型配置」的嵌入 dim 从未接入实际调用链：嵌入客户端构造与 Qdrant 集合 size
都只读 KB 配置 `embedding_dim`，模型配置条目仅覆盖 base_url/model/api_key 三字段。
表单 dim 沦为校验/展示字段，两处配置漂移无感知。
次因：模型配置端点不清 `kb.embed` 的 `_dense/_sparse` 缓存，配置变更需重启进程才生效。

## 改动范围

| 文件 | 改动 |
|---|---|
| backend/kb/embed.py | 新增 `effective_dim()`（模型配置 dim>0 优先，否则回退 KB 配置）；`_ensure_dense` 的 `dimensions` 改用该函数 |
| backend/kb/store.py | `_vectors_config` 建集合 size 改用 `embed.effective_dim()`；移除未用 settings 导入 |
| backend/memory/vector.py | `ensure_collection` 同上；移除未用 settings 导入 |
| backend/main.py | 模型 create/update/delete 端点调用 `_reset_embed_clients()` 清嵌入客户端缓存 |
| backend/tests/test_kb_embed_sparse.py | 3 个回归测试 + autouse 模型库隔离 fixture |

设计原则：模型配置成为嵌入「模型+维度」的单一事实来源；无默认嵌入条目时行为与原先完全一致（回退 KB 配置/env），存量集合不受影响（size 建库时已固化）。

## 回归测试

`tests/test_kb_embed_sparse.py::test_dense_client_dimensions_from_model_store`、
`::test_effective_dim_prefers_model_store_and_falls_back`、
`::test_create_kb_collection_uses_model_store_dim`（均先红后绿）。

## 验证结果

- 定向：6 passed；全量：216 passed（backend/venv, pytest）
- 待办：重启后端后 UI 端到端验证（设默认嵌入 dim → 新建知识库 → 集合 size 一致）

## 已知边界（本次不做）

- 更换不同 dim 的嵌入模型后，存量集合需删除重建，UI 暂无提示
- 部分 OpenAI 兼容网关不接受 `dimensions` 参数，暂无"不发送"开关
