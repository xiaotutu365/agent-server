# 修复清单：embed-dim-not-applied

## 诊断

- [x] 复现路径确认：`_ensure_dense` 只覆盖 base_url/model/api_key，dimensions 恒取 KB 配置；建集合 size 同只读 KB 配置（store.py / memory/vector.py）
- [x] 附带发现：模型配置 create/update/delete 端点不清 `kb.embed` 客户端缓存，改配置需重启进程才生效

## 回归测试（先红后绿）

- [x] `test_dense_client_dimensions_from_model_store`：默认嵌入条目 dim=1024 应覆盖 dimensions —— 红（实际 256）→ 绿
- [x] `test_effective_dim_prefers_model_store_and_falls_back`：effective_dim 优先级与回退 —— 红（AttributeError）→ 绿
- [x] `test_create_kb_collection_uses_model_store_dim`：新建集合 size 与模型配置同源 —— 红（size=256）→ 绿
- [x] 模块内加 autouse `_isolated_model_db`，避免真实 agent_sessions.db 泄漏进断言

## 实现

- [x] `kb/embed.py` 新增 `effective_dim()`；`_ensure_dense` 的 dimensions 改用该函数
- [x] `kb/store.py::_vectors_config` 建集合 size 改用 `embed.effective_dim()`（清理未用的 settings 导入）
- [x] `memory/vector.py::ensure_collection` 同上（清理未用的 settings 导入）
- [x] `main.py` 模型 create/update/delete 端点补 `_reset_embed_clients()`

## 验证

- [x] `pytest tests/test_kb_embed_sparse.py -q` → 6 passed
- [x] `pytest tests -q` 全量 → 216 passed
- [ ] 端到端：重启后端后，在「模型配置」设默认嵌入 dim 并新建知识库验证 size（待人工执行/重启后验证）
