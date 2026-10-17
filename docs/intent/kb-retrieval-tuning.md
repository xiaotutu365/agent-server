# 意图声明：知识库检索调优（向量权重 + 相似度阈值）

- 确认时间：2026-10-17
- 确认方式：对话确认（参考 RAGFlow Search Settings 文档，用户选定范围与落点）

## Outcome

参考 RAGFlow 搜索设置，补齐知识库检索策略两项缺失能力：

1. **向量权重 `vector_weight`**：混合检索中 dense 语义与 sparse 关键词的相对权重（0.3 = 向量 0.3 / 全文 0.7）。调高偏语义匹配（用户措辞与原文差异大），调低偏关键词精确匹配（专有名词、型号）。
2. **相似度阈值 `similarity_threshold`**：过滤相关性低于阈值的片段，减少无关结果。

## User / Why now

- 用户：知识库管理员。
- 动机：对照 RAGFlow 盘点发现，检索策略 9 项中我们已有 rerank candidates（candidate）、rerank model（`_maybe_rerank`）、datasets（agent 挂载）、chunk metadata（引用 badge），唯缺向量权重与相似度阈值；评测页调参闭环需要更完整的检索控制面。

## Success

- 全局设置面板可调两项参数，保存即对所有知识库检索生效。
- `vector_weight=0.5`、`similarity_threshold=0` 时检索行为与现版本完全一致（向后兼容）。
- 阈值过滤在配置 rerank 模型时用 rerank 分，否则用 dense cosine 分。

## Constraint（已确认决策）

- **范围**：只补检索策略 2 项；RAGFlow 的 AI summary / related search / query mindmap 为独立搜索应用的展示层功能，与 agent 聊天内嵌检索场景不匹配，不做。
- **落点**：全局设置面板（沿用分片策略的全局一处设置惯例），不按库独立配置。
- **实现方式**：向量权重用加权 RRF（dense 贡献 w、sparse 贡献 1-w），不做分数加权融合（两路量纲不同，归一化不可靠）。
- **阈值分数源**：RRF 分不归一不可作阈值；按优先级取 rerank relevance_score → dense cosine 分；纯 BM25 召回（无 cosine 分）的片段保留不误杀；dense 降级时整体跳过过滤。

## Out of scope

- AI 摘要、相关搜索、查询思维导图（展示层，与聊天场景不匹配）。
- 按知识库独立检索参数（schema/UI/传参改动面大，无现实需求）。
- rerank 模型配置本身（已有，model_store 默认 rerank 模型机制不动）。
