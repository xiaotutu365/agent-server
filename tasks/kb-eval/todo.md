# Todo: 知识库检索评测

## Phase 1: 后端（TDD）

- [x] **T1 评测模块后端**（M，TDD）
  - 验收：recall@k/MRR 计算正确；evalset 模板/校验；run 双轨降级不 5xx
  - 验证：`tests/test_kb_eval.py` 10 passed（先红后绿）；全量 77 passed
  - 依赖：ragas 安装完成
  - 涉及：`kb/eval.py`（新）、`kb/api.py`、`tests/test_kb_eval.py`（新）
  - 记录：ragas 懒导入——测试不依赖 ragas 包；judge LLM 走 `model_store.get_default_sync("chat")`；ragas 在 `asyncio.to_thread` 中执行避免阻塞事件循环

## Phase 2: 前端

- [x] **T2 评测模态窗**（M）
  - 验收：评测集 JSON 可编辑保存；运行后展示汇总指标 + 逐条召回片段（hit 标记）
  - 验证：`vite build` 通过
  - 依赖：T1
  - 涉及：`frontend/src/api/kb.js`、`frontend/src/components/KnowledgeBase.vue`
  - 记录：运行前自动保存 textarea 内容，保证「看到的=运行的」；复用全局 `.modal/.badge` 设计系统

## Phase 3: 收尾

- [x] **T3 验证 + review**（S）
  - 验收：spec L6 验收两条全过；review 问题清零
  - 验证：pytest 77 passed / build 通过 / API 冒烟（GET 模板 200、非法 PUT 400、run 无 embedding 时 400 带指引非 5xx）
  - 依赖：T1 T2
  - 记录：线上真值评测需先配置 embedding 服务（DeepSeek 无此端点）；ragas 指标另需默认 chat 模型作 judge

