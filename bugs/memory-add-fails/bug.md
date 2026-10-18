# Bug：无法添加记忆（POST /api/memory 挂起且阻塞全后端）

- 发现时间：2026-10-18
- 发现方式：用户反馈前端「无法添加记忆」→ API 复现

## 现象

- 记忆管理页「手动添加」一直转圈，最终失败
- 复现：`POST /api/memory`（body `{"content": "..."}`）挂起 >60s 无响应；期间**整个后端冻结**（连 `POST /api/auth/login` 都超时）

## 复现证据

```
ERROR | fastembed download_model:712 - Could not download model from HuggingFace: timed out
ERROR | fastembed download_model:746 - Could not download model from either source, sleeping 3.0s, 2 retries left
（3s/9s/27s 退避重试共约 60s 后）
ValueError: Could not load model Qdrant/bm25 from any source.
```

- `~/.cache/fastembed` 为空：`Qdrant/bm25` 本地缓存缺失，每次冷启动需重新下载
- 前端记忆管理页正常打开（GET /api/memory 200），仅添加失败

## 根因（两层叠加）

1. **环境层**：bm25 稀疏模型缓存缺失 + HuggingFace 直连超时。`vector.upsert_memory → embed.embed_query → _ensure_sparse()` 触发 fastembed 联网下载，网络不通时重试约 60s 后抛错
2. **代码层**：
   - [memory/api.py] `create_memory`（async）直接调用同步阻塞的 `vector.upsert_memory`（内含 embedding 网络调用 + Qdrant 写入），**阻塞事件循环**，期间所有 API 无响应
   - `store.add_memory` 已入库后才因向量失败抛 500 → 用户重试会产生**重复记忆**

## 修复方向

- 代码：vector 调用改 `asyncio.to_thread` 不阻塞事件循环；向量写入失败不 500（记忆本体已存，与模块「embedding 故障静默不阻断」哲学一致），记 warning 日志
- 环境：预下载 bm25 模型到本地缓存（HF_ENDPOINT=https://hf-mirror.com），避免运行时联网
