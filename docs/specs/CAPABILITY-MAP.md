# 全局能力地图

> 模块索引与依赖方向。新增模块 spec 按此登记；模块间契约写入**提供方模块**的 spec。

## 模块表

| 模块 | spec | 职责 | 依赖（→ 被依赖） |
|---|---|---|---|
| auth-rbac | —（沿用现状） | 登录、角色、部门、用户、接口权限闸 | → 全部管理端点 |
| chat-agent | —（沿用现状） | 聊天流式（SSE）、agent 实例缓存（AGENT_CACHE） | kb, mcp, tools → 前端 ChatView |
| agent-config | —（沿用现状） | agent 配置存取（SQLite agent_config 表）、热重建 | → chat-agent |
| tools | —（沿用现状） | 内置工具目录与注册表（tool_registry 分组） | → chat-agent |
| mcp | —（沿用现状） | MCP 服务器接入、挂载、权限闸 | → chat-agent |
| hitl | [SPEC-hitl](SPEC-hitl.md) | 人机交互中断/恢复 | → chat-agent |
| knowledge-base | [SPEC-knowledge-base](SPEC-knowledge-base.md) | 文档入库、混合检索、Agent 挂载、引用来源 | → chat-agent（kb 工具） |

## 依赖方向（谁依赖谁）

```
frontend (Vue3) ──► REST/SSE ──► main.py (FastAPI)
                                   ├── auth-rbac（权限闸）
                                   ├── agent-config ──► chat-agent
                                   ├── knowledge-base ──┐
                                   ├── mcp ─────────────┤
                                   └── tools ───────────┴──► deep_agent (LangGraph)
```

## 构建顺序约定

后端能力自底向上：先存储/引擎（Qdrant、SQLite），再 API，再 Agent 集成，最后前端 UI。
当前活跃工作：knowledge-base 四层（环境 → 文档管理 → 检索调优 → Agent 挂载），见 SPEC-knowledge-base。
