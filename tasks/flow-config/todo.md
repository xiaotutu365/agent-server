# Todo: flow-config M1 后端内核

## Phase 1: 内核（TDD）

- [x] T1 store 层 `backend/flow/store.py`（S）
  - 验收：flows/flow_runs 建表幂等；flow CRUD 与 run 状态流转（running/waiting_human/done/failed/cancelled）可测
  - 验证：tests/test_flow_store.py（monkeypatch DB_PATH 到 tmp）——7 用例绿
- [x] T2 DSL 校验 `backend/flow/dsl.py`（S）
  - 验收：合法 definition 通过；缺 entry/未知节点类型/边引用不存在节点/缺 output_key/条件边 when 非法值 → 带字段名的错误信息
  - 验证：tests/test_flow_dsl.py——12 用例绿（entry 改为显式字段：修订回环下「无入边即入口」规则失效）
- [x] T3a runner 线性执行 `backend/flow/runner.py`（M）
  - 验收：llm 节点（fake agent 工厂注入）→ tool 节点（REGISTRY 真工具或 fake）顺序执行；`${output_key}` 插值；state/outputs 落库
  - 验证：tests/test_flow_runner.py——10 用例绿（含人审暂停时 outputs 增量落库回归）
- [x] T3b runner 人审 + 条件 + 守卫（M）
  - 验收：human 节点 interrupt 暂停（status=waiting_human）；Command(resume) 继续；when 条件路由；max_revisions 超限 failed
  - 验证：tests/test_flow_runner.py（interrupt 用 langgraph 内存 checkpointer）

## Checkpoint 1：全量 pytest 绿（196 通过），内核无 API 依赖可独立测试 ✅

## Phase 2: API 与接线

- [x] T4 API router `backend/flow/api.py`（M）
  - 验收：8 端点按 spec 3.4；CRUD 走 require_admin；发起/审批 get_current_user；definition 非法 400；SSE 事件含 flow_step/token/done/error
  - 验证：tests/test_flow_api.py——12 用例绿。期间修复：执行中重复 resume 400（_INFLIGHT 防并发恢复，回归钉住）；resume 等待用 updated_at 判别段落（FakeAgent 下执行段快于轮询间隔，中间态 running 不可观察）
- [x] T5 main.py 接线 + 冒烟（S）
  - 验收：router 注册；curl 发起→人审→resume→done 全链路 SSE 正确；重启后端后 waiting_human 的 run 可 resume（checkpointer 持久化）
  - 验证：curl 实测——线性 done、人审暂停 pending/outputs 可见、跨进程恢复（重启后 resume→done）、SSE 快照+历史回放+实时跟随、rejected 回环二次人审、max_revisions=1 二次 rejected 守卫 failed（error 落库）

## Checkpoint 2：全量测试 209 绿 + 端到端通过，向用户汇报 M1 完成 ✅
