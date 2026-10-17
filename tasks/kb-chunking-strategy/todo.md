# Todo: 知识库分片策略

## Phase 1: 后端（TDD）

- [x] **T1 分片策略后端**（M，TDD）
  - 验收：三策略 `_split` 行为符合 spec 表格；非法策略 400
  - 验证：`./venv/bin/python -m pytest tests/test_kb_chunking.py -q` 先红后绿
  - 依赖：无
  - 涉及：`kb/settings.py`、`kb/ingest.py`、`kb/api.py`、`tests/test_kb_chunking.py`

## Phase 2: 前端

- [x] **T2 设置面板策略下拉**（S）
  - 验收：下拉含三策略（枚举来自 API），保存后提示「仅对之后上传的文档生效」
  - 验证：vite build + HMR 无报错
  - 依赖：T1
  - 涉及：`frontend/src/components/KnowledgeBase.vue`

## Phase 3: 收尾

- [x] **T3 验证 + review**（S）
  - 验收：spec L5 验收两条全过；review 问题清零
  - 验证：pytest 全量 / build / 浏览器冒烟
  - 依赖：T1 T2
  - 涉及：`tasks/kb-chunking-strategy/todo.md` 勾选与验证记录
  - **验证记录（2026-10-17）**：
    - pytest 67 passed（含新增 `test_kb_chunking.py` 9 用例：三策略切分/兜底/未知策略回退/校验 400/API 契约）
    - `vite build` 通过；重启后端后实测 `GET /api/kb/settings` 返回 `chunk_strategy=fixed` 与三策略枚举
    - 浏览器冒烟 6/6：设置面板下拉三选项、说明文字、切换保存含「仅对之后上传的文档生效」提示、恢复默认
    - review：实现与 spec L5 一致；非法值白名单校验在 save_settings 边界；UI 枚举带本地兜底；无越界改动
