# 会话级模型选择

Spec：docs/specs/SPEC-session-model-select.md（2026-10-18 评审通过）

## Phase 1 后端（TDD）

- [x] T1 失败测试：thread_meta get/set/delete；build_agent(model_id=...) 用指定模型（桩断言 get_model 被用、extra 参数生效）；get_agent_for 缓存键含 model 维度、model_id 空时键与现在完全一致（tests/test_session_model.py）
- [x] T2 实现 T1：agent/thread_meta.py（新）+ deep_agent.build_agent 增加 model_id 覆盖 + main.get_agent_for 缓存键扩展；T1 转绿
- [x] T3 失败测试：ChatRequest.model_id 非空 → thread_meta 写入且 agent 收到覆盖；模型已删 → 清覆盖回退默认不报错；GET /api/threads 返回 model_id；DELETE 会话级联清理；GET /api/models/chat 普通用户可访问且不含 api_key/base_url；模型 PUT/DELETE 后 AGENT_CACHE 被清空
- [x] T4 实现 T3：main.py（ChatRequest 字段、chat_stream 持久化与校验、threads/messages/delete、/api/models/chat、admin models 失效缓存）；T3 转绿
- [x] ✅ Checkpoint 1：pytest 全量通过（存量用例无回归），curl 验证 /api/models/chat 与会话覆盖持久化

## Phase 2 前端

- [x] T5 api/chat.js streamChat 增加 modelId 参数（仅非空携带）；api/models.js 增加 listChatModels()
- [x] T6 ChatView.vue：顶栏「模型」下拉（默认（跟随全局）+ llm 列表）；新会话默认「默认」；switchThread 按 model_id 回显；切换模型不开新会话；发送时携带 model_id

## Phase 3 验证与收尾

- [x] ✅ Checkpoint 2：pytest 全量 + npm run build 通过（164 passed；build 554ms）
- [x] T7 浏览器冒烟：切模型发消息（新模型生效、历史不变）、切会话回显、存量会话显示「默认」、普通账号可用；通过后提交

## 冒烟记录（2026-10-18）

- 下拉候选：GET /api/models/chat 正常，「默认（跟随全局）」+「DeepSeek Chat（默认）」两项
- 选中 DeepSeek Chat 发消息：AI 走覆盖模型回复「成功」；thread_meta 落库（`u{uid}:ls52ryjjmv849q2m` → b5640885）
- 新建会话：模型下拉回到「默认（跟随全局）」
- 切回原会话：回显「DeepSeek Chat（默认）」，历史 16 条完整不变
- 刷新页面：持久化回显保持，历史恢复
- 注：model_configs 原为空库，为冒烟用 .env 同款配置创建了默认条目 DeepSeek Chat（id b5640885-abb6-41fb-9f0b-c5a989a1bceb）
