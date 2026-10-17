# 计划：知识库检索调优（向量权重 + 相似度阈值）

意图：docs/intent/kb-retrieval-tuning.md（2026-10-17 已确认）
Spec：docs/specs/SPEC-knowledge-base.md 能力 L8

## 设计决策

1. **向量权重 → 加权 RRF**：`_rrf` 支持 per-list 权重，dense 贡献 `w/(k+rank+1)`、sparse 贡献 `(1-w)/(k+rank+1)`。不用分数加权融合——dense cosine 与 BM25 分量纲不同，归一化不可靠。
2. **阈值分数源优先级**：rerank relevance_score（配置了 rerank 模型时）→ dense cosine 分（无 rerank 时）。RRF 分不归一，不可作阈值。
3. **不误杀规则**：纯 sparse 召回（无 cosine 分）的片段保留；dense 降级（纯 BM25）整体跳过过滤。
4. **向后兼容**：`vector_weight=0.5`、`similarity_threshold=0.0` 为默认值，行为与现版本一致。

## 改动面（M 级，5 文件）

| 文件 | 改动 |
|---|---|
| backend/kb/settings.py | DEFAULTS 增 2 字段 + save_settings 数值校验（非法 ValueError → API 400） |
| backend/kb/retrieval.py | `_rrf` 加权；`hybrid_search_ex` 保留 cosine 映射 + 阈值过滤；`_maybe_rerank` 返回分数；签名增 2 个可选参数 |
| backend/tests/test_kb_retrieval.py | 加权 RRF / 阈值过滤 / 运行时覆盖（TDD 先行） |
| backend/tests/test_kb_settings_api.py（或就近文件） | 非法值 400 |
| frontend/src/components/KnowledgeBase.vue | 设置面板 2 个输入项 + 表单默认值 |

## 验证

- `pytest backend/tests/` 全绿（现 95+ 用例回归一致）
- `npm run build` 通过
- 手动冒烟：调高阈值 → 工作区检索低相关片段被滤除；恢复默认 → 行为不变
