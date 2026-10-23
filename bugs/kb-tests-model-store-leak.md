# kb 测试泄漏真实 model_configs 状态（单文件小修）

## 现象

用户在「模型配置」添加 dim=1024 的嵌入模型后，`backend/tests/test_kb_*.py` 全挂：
`Vector dimension error: expected dim: 1024, got 1536`。

## 根因

`kb/embed.effective_dim()` 优先读 `agent.model_store.get_default_sync("embedding")`（真实 DB）。
conftest 的 `isolated_settings` 只隔离了 `kb_settings.json`，未隔离 model_configs 表；
fake_embed 按 `cfg.EMBEDDING_DIM=1536` 造向量，建集合却用真实条目的 1024。
此前 216 项测试通过是因为 model_configs 恰好为空——测试依赖了外部状态。

## 修复

conftest 增加 autouse 夹具：monkeypatch `agent.model_store.get_default_sync` 返回 None，
使测试回退到已隔离的 KB 默认配置。

## 验证

`pytest tests/test_kb_ingest.py` 及全量 kb 测试通过，不依赖 data/ 目录状态。
