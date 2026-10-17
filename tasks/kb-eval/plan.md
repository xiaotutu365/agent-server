# Plan: 知识库检索评测（kb-eval）

> Spec: `docs/specs/SPEC-knowledge-base.md` 能力 L6；意图: `docs/intent/kb-eval.md`；选型: `docs/adr/ADR-002-ragas-eval.md`

## 思路

新模块 `kb/eval.py`：评测集文件读写（含模板）、Recall@k/MRR 计算、run_eval（自算 + Ragas 双轨降级）。API 三端点（evalset GET/PUT + run）。前端 KnowledgeBase.vue 加「评测」模态窗。Ragas 懒导入，judge LLM 缺配置时降级。

## 任务

- **T1 后端评测模块**（M，TDD）：eval.py（evalset 读写/模板、recall@k/mrr、run_eval 双轨）；api.py 三端点。测试 `tests/test_kb_eval.py`
- **T2 前端评测模态窗**（M）：评测按钮 + 模态窗（评测集 JSON 编辑/保存/运行/结果展示）
- **T3 验证 + review**（S）：pytest 全量 / build / 浏览器冒烟 / 勾选与验证记录

## Checkpoint

- T1 后：pytest 全绿（ragas 装完）
- T3 后：spec L6 验收两条全过
