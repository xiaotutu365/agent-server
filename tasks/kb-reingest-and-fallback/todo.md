# 知识库重新入库 + 检索失败兜底

意图：docs/intent/kb-reingest-and-fallback.md（2026-10-17 已确认）

## Phase 1 后端

- [x] T1 留档：上传成功后保存原文件到 data/uploads/{kb_id}/（文件名清洗、同名覆盖、失败不阻断）
- [x] T2 reingest：ingest.reingest_document(kb_id, source)——删旧片段 → 留档重新入库；POST /api/kb/{kb_id}/documents/reingest?file=（无留档 404）；TDD（5 测试）
- [x] T3 兜底：embed.sparse_query() + hybrid_search_ex 降级纯 BM25（任何 dense 侧故障含网络错误）+ 零结果也透出 fallback；search API 顶层 fallback 字段 + 工具输出 fallback；TDD（5 测试）
- [x] T3.1 冒烟修正：embedding「配置了但连不上」抛的是 openai 连接错误而非 EmbeddingUnavailable，扩大捕获为 Exception

## Phase 2 前端

- [x] T4 kb.js reingestDocument + KnowledgeBase.vue 文档行「重新入库」按钮（confirm→调用→刷新）+ 检索降级提示条（读顶层 fallback）

## Phase 3 验证与收尾

- [x] T5 pytest 全量 95 passed + npm build + 冒烟：docx 上传留档 ✓ / 重新入库成功 ✓ / 旧文档无留档 404 提示 ✓ / 挂掉 embedding 检索降级提示 ✓ / 恢复后正常 ✓
- [x] T6 SPEC L7 节 + 追溯更新（代码未提交，与引用原文查看、评测独立页一起提交）

## 发现与决策记录

- pdf/docx 上传经核对已实现（pypdf 6.20.1 / python-docx 1.2.0 已装、前后端已放开），本验收过 docx 上传，无需新开发
- fastembed Qdrant/bm25 对中文按空白分词，中文语料降级召回可能为零——机制可用、质量受限，零结果时透出降级原因缓解困惑（SPEC L7 已记）
