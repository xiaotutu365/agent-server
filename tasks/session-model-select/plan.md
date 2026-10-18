# 会话级模型选择 — 实施计划

Spec：docs/specs/SPEC-session-model-select.md（2026-10-18 评审通过）

## 切分思路（垂直切片）

- 切片 1（后端全链路）：完成后 `/api/models/chat` 与 `model_id` 覆盖可用 curl 验证，会话覆盖持久化生效
- 切片 2（前端全链路）：在切片 1 之上接通 UI，用户可见可切
- 验证收尾：全量测试 + 浏览器冒烟

## 关键实现点

1. `agent/thread_meta.py`（新）：`get_thread_model / set_thread_model / delete_thread_meta`，aiosqlite，表 `thread_meta(thread_id PK, model_id, updated_at)`；`thread_id` 用带用户前缀的 lg_thread（`u{user_id}:{thread_id}`），天然用户隔离
2. `deep_agent.build_agent(config, system_prompt=..., model_id=None)`：model_id 非空时 `get_model(model_id)` 替代 `get_default("llm")`（extra 高级参数同样生效）；注意 model_store 查询异常时的兜底路径（现 llm_cfg 在 try 外被引用，覆盖路径不得复制该隐患）
3. `main.get_agent_for(system_prompt, agent_id, model_id=None)`：缓存键 `{原key}::model:{model_id}`；model_id 为空走原键（存量行为不变）
4. `chat_stream`：model_id 非空 → 校验 type=llm → `set_thread_model`；模型已删 → warning 日志 + 清覆盖记录 + 回退默认
5. `GET /api/threads` 附带 model_id；`DELETE /api/threads/{id}` 删 thread_meta
6. `GET /api/models/chat`（登录即可）：type=llm，仅返回 {id, name, model, is_default}
7. `PUT/DELETE /api/admin/models/{id}` 后 `AGENT_CACHE.clear()`（本功能引入按模型缓存，防陈旧实例）
8. 前端：ChatView 顶栏「模型」下拉（复用 head-agent 样式，「默认（跟随全局）」空值选项）；switchThread 按 threads.model_id 回显；切模型不开新会话；streamChat 增加 model_id 参数（仅非空携带）

## 风险与注意

- `AGENT` 全局实例启动时构建，模型配置更新不重建（现状如此，不在本次范围）；会话覆盖路径走 AGENT_CACHE，不受影响
- 回归风险点：model_id 为空时所有既有键/行为必须逐字节不变（存量会话向后兼容的验收线）
