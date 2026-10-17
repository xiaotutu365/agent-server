# Bug: 智谱 embedding 联调暴露的三个潜在缺陷（fastembed API / dimensions / source 文件名）

> 2026-10-17，配置智谱 embedding-3 跑真实链路时发现。测试环境全 mock embed 层，此前均不可见。三个缺陷一行级修复，按规范合并单文件记录。

## 现象与根因

1. **入库失败 `SparseTextEmbedding has no attribute 'embed_documents'`**
   - 根因：fastembed 的稀疏模型只有 `.embed()` 方法；[embed.py](../../backend/kb/embed.py) 误用 `.embed_documents()`/`.embed_query()`（从未被真实执行过）
   - 修复：统一改为 `.embed(texts)` / `.embed([text])`
2. **入库失败 `expected dim: 1024, got 2048`**
   - 根因：langchain `OpenAIEmbeddings` 默认不传 `dimensions`，智谱 embedding-3 默认输出 2048 维，与建库集合 schema（settings.embedding_dim=1024）不符
   - 修复：`_ensure_dense()` 显式传 `dimensions=embedding_dim`
3. **检索结果 source 显示 `tmpu7ni_i17.md`**
   - 根因：上传走 `tempfile.mkstemp`，`ingest_file` 用临时路径 basename 作为 payload.source
   - 修复：`ingest_file(..., source=原始文件名)`，api.py 传 `file.filename`；点 id 种子同步用原始名（同文件重传幂等）

## 环境备注

- fastembed BM25 模型下载需 `HF_ENDPOINT=https://hf-mirror.com`（后端启动环境变量），官方源不通

## 回归测试

- `tests/test_kb_embed_sparse.py`：桩钉住 fastembed「只有 .embed() 且产出 numpy」契约 + dimensions 传参断言（先红后绿）
- `tests/test_kb_ingest.py::test_ingest_source_uses_original_filename`：source 必须为原始文件名
- conftest 新增 `isolated_settings`：屏蔽真实 `data/kb_settings.json` 泄漏进测试（1024 维配置曾致 12 个用例维度冲突）

## 验证结果

- pytest 81 passed；vite 构建通过
- 真实链路（智谱 embedding-3 dense + fastembed BM25 sparse）：入库 → 混合检索（score/来源正确）→ 评测 run（recall@k=1.0, MRR=1.0, ragas 缺包时优雅降级）
