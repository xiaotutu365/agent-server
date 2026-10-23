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

---

# Todo: flow-config M2 前端（spec 3.5）

## Phase 3: 管理页

- [x] T6 api/flows.js + FlowView 管理页（M）
  - 涉及：frontend/src/api/flows.js（新建）、frontend/src/views/FlowView.vue（新建）、router/index.js、AdminLayout.vue
  - 验收：列表展示 name/version/更新时间；新建/编辑弹窗（name + definition JSON textarea），非法 JSON 前端拦截、后端 400 detail 展示；删除有确认
  - 验证：浏览器实测 CRUD 全流程 + 非法 JSON 拦截（CP3）

## Phase 4: 运行页与人审

- [x] T7 FlowRunView 发起 + 实例列表 + SSE 时间线（M）
  - 涉及：frontend/src/api/flows.js（扩展 SSE）、frontend/src/views/FlowRunView.vue（新建）、router/index.js
  - 验收：选流程 + 输入 JSON 发起；实例列表状态徽章/当前节点；详情页 SSE 逐节点 flow_step/flow_status 时间线，done/failed/cancelled 收尾
  - 验证：浏览器实测发起→逐节点可见→done（CP4 前半）

- [x] T8 人审交互 + 取消（S）
  - 涉及：frontend/src/views/FlowRunView.vue
  - 验收：waiting_human 时展示 pending.prompt + 已产出 outputs；批准/拒绝(+意见) POST resume `{"decision","comment"}`；rejected 回环可二次审批；取消按钮生效
  - 验证：浏览器实测人审闭环（CP4 后半）

## Checkpoint 3：浏览器实测 CRUD + 非法 JSON 前端拦截 + 后端 400 detail 就地展示 + 删除确认，console 无 error ✅

## Checkpoint 4：浏览器实测全链路 ✅——发起→SSE 逐节点→等待审批→拒绝(+意见)回环修订→二次审批→批准→publish→done+final 产出；第二条实例取消生效（已取消）；console 无业务 error

## Phase 5: 回归验收

- [x] T9 端到端示例流程 + 全量回归（S）
  - 验收：页面配置「llm 生成→human 审批→llm 修订回环→done」示例流程并全链路跑通；backend 全量 pytest 绿
  - 验证：browser E2E ✅ + pytest 209 passed ✅

## Checkpoint 5：M2 前端完成（CP3/CP4/CP5 全过），待用户验收
