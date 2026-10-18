# 修复记录：无法添加记忆（POST /api/memory 挂起且阻塞全后端）

- 修复时间：2026-10-18
- 问题与证据：见 [bug.md](bug.md)

## 根因

两层叠加：

1. **环境**：`~/.cache/fastembed` 为空，`Qdrant/bm25` 模型未缓存；`_ensure_sparse()` 冷启动触发 HuggingFace 联网下载，直连超时（3s/9s/27s 退避共约 60s 后 `ValueError: Could not load model Qdrant/bm25 from any source`）
2. **代码**：`memory/api.py` 的 async 处理器直接调用同步阻塞的 `vector.*`（内含 embedding 网络调用 + Qdrant HTTP），**阻塞事件循环**——单个慢请求冻结整个后端；且 `store.add_memory` 已入库后才抛 500，重试产生重复记忆

## 改动

| 文件 | 改动 |
|---|---|
| backend/memory/api.py | `create_memory / set_enabled / forget_memory` 中 `vector.*` 全部改 `asyncio.to_thread`；`create_memory` 向量写入失败仅 warning 不 500（记忆本体已入库，与模块「embedding 故障静默」哲学一致） |
| backend/memory/extract.py:84 | 抽取路径 `vector.upsert_memory` 同样改 `to_thread`（外层已有静默 except） |
| 环境（无代码） | `HF_ENDPOINT=https://hf-mirror.com` 预下载 `Qdrant/bm25` 到 `~/.cache/fastembed`（18 文件，3s） |

- set_enabled/forget 的 to_thread 失败仍抛（500）：二者不涉及 embedding，Qdrant 故障应暴露给管理端

## 回归测试（TDD，tests/test_memory_api.py 新增 2 例）

- `test_post_survives_vector_failure`：monkeypatch `upsert_memory` 抛 ConnectionError → POST 仍 200 且列表可见（先红：ConnectionError 直抛 500）
- `test_post_offloads_vector_to_thread`：probe 检查执行线程无 running loop（先红：`blocking: True` 在事件循环线程同步执行）

## 验证

- pytest 全量 139 passed（新增 2 例 + 回归）
- 服务端到端：POST /api/memory **0.54s 返回 200**（原 >60s 挂死），列表/删除正常
- KB 检索同步恢复：bm25 缓存就位后 `smoke_zhipu` 检索 2 条正常返回
- 冒烟残留记忆已清理

## 遗留观察

- 若换机器/清缓存后再次冷启动，仍需联网下载 bm25（或设 HF 镜像）。后续可考虑将 fastembed 缓存目录纳入项目（`cache_dir` 参数）或启动时预热，当前未做（避免过度设计）
