# ADR-002: 检索评测用 Ragas，指标双轨（自算 Recall/MRR + Ragas context 指标）

- **状态**: Accepted
- **日期**: 2026-10-17
- **关联**: [SPEC-knowledge-base.md 能力 L6](../specs/SPEC-knowledge-base.md)、[intent/kb-eval.md](../intent/kb-eval.md)

## 背景

需要评测能力指导分片策略/检索参数选择。用户在 interview 中明确两个诉求：① 检索层指标（召回率等）；② 逐条查看召回片段。框架选择上用户倾向 Ragas（看重其 LangChain 生态适配）。

## 决策

**本期直接引入 Ragas**（用户选定），但采用**指标双轨**：

1. **自算 Recall@k / MRR**（零 LLM，始终可用）：以评测集 `expected_files`（文件级标注）为 ground truth。Ragas 的 context 指标没有「文件级 ground truth」的现成实现，且 MRR 不在其指标集中，故自算（集合运算，约 20 行）。
2. **Ragas context_precision / context_recall**：仅对提供 `reference`（期望片段原文或参考答案）的条目计算，judge LLM 用项目 model_store 默认模型；不可用时优雅降级为只跑自算。

**评测集双字段设计**（`expected_files` + `reference?`）是双轨的直接结果：文件级标注驱动自算指标（标注成本最低），可选的 reference 文本解锁 Ragas 指标（标注成本高但更细）。

## 被否掉的备选方案

1. **纯自研（本期不引入 Ragas）**：最初推荐方案。用户权衡后认为 Ragas 的 LangChain 适配与二期演进（TestsetGenerator 自动生成评测集、faithfulness 等生成层指标）值得本期落地依赖——按用户判断采纳 Ragas。
2. **DeepEval / TruLens / Deepchecks**：DeepEval 偏 CI 单测风格；TruLens/Deepchecks 偏生产监控平台，对单机项目过重。

## 后果

- 新增依赖 ragas（连带 datasets/pandas 等，安装体积较大）
- 评测集标注有两档成本：只填 `expected_files` 即可跑自算指标；填 `reference` 解锁 Ragas 指标
- 二期演进路径明确：评测集编辑 UI → TestsetGenerator 自动标注 → 生成层指标
