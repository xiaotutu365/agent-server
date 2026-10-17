# Intent: 知识库检索评测（kb-eval）

> interview-me 产出，用户已明确确认（2026-10-17）。

## 背景与问题

分片策略与检索参数（top_k/candidate/rrf_k）已可配置，但效果只能凭感觉判断。需要评测能力作「标尺」：换策略/调参前后跑一遍，指标说话。

## 目标

知识库工作区新增「评测」入口（模态窗）：选库 → 运行 → 展示指标 + **逐条召回片段**（内容/排名/是否命中期望文件）。

### 指标双轨

1. **自算**（零 LLM，始终可用）：Recall@k、MRR——按评测集 `expected_files` 计算
2. **Ragas**（context_precision / context_recall，LLM-as-judge 用项目 model_store 默认模型）——仅对提供 `reference`（期望片段原文或参考答案）的条目计算；judge LLM 不可用时自动降级只跑自算

### 评测集

- `backend/data/kb_eval_<kb_id>.json` 手工维护：`[{"query", "expected_files", "reference"?}]`
- 先提供 3-5 条示例模板（GET 无文件时返回模板供 UI 预填）

## 用户明确的选择

- **评测范围**：本期只评检索层（生成层二期）
- **框架**：本期直接上 Ragas（用户选定，看重其 LangChain 生态适配与二期演进）；检索层 Recall@k/MRR 因 Ragas 无文件级 ground truth 现成指标，仍自算
- **评测集编辑 UI**：不做，列入二期
- **新依赖**：ragas（用户批准）

## 成功标准

- 选库跑评测出两组指标；召回片段逐条可见可比对
- pytest 全绿；ragas 缺 judge LLM 时优雅降级不报错

## 明确不做（Out of scope，二期候选）

- 评测集编辑 UI、Ragas TestsetGenerator 自动生成评测集
- faithfulness / answer relevancy 等生成层指标
- LLM 评分、自动回归、多库横向对比
