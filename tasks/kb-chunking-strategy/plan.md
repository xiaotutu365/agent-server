# Plan: 知识库分片策略（kb-chunking-strategy）

> Spec: `docs/specs/SPEC-knowledge-base.md` 能力 L5；意图: `docs/intent/kb-chunking-strategy.md`；选型: `docs/adr/ADR-001-langchain-text-splitters.md`

## 思路

全局设置 `chunk_strategy`（fixed/markdown/blank_line，默认 fixed=现行为），`kb/ingest.py._split` 按策略分发到对应切分器；markdown/blank_line 策略下超长片段用 Recursive 兜底切。前端设置面板加策略下拉，保存后提示仅对新上传生效。

## 任务

- **T1 后端分片策略**（M，TDD）：settings 增 `chunk_strategy` + `CHUNK_STRATEGIES` 校验（非法 400）；`_split` 三策略分发；GET settings 返回枚举说明。测试 `tests/test_kb_chunking.py`
- **T2 前端设置面板**（S）：KnowledgeBase.vue 设置区加「分片策略」下拉 + 「仅对之后上传的文档生效」提示
- **T3 验证 + review**（S）：pytest 全绿 / vite build / 浏览器冒烟

## Checkpoint

- T1 后：pytest 全绿
- T3 后：整体验收（spec L5 验收两条）
