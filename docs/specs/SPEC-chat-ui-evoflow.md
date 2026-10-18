# SPEC：聊天窗口 EvoFlow 风格改版

- module-id：`chat-ui-evoflow`
- 日期：2026-10-18
- 意图：[docs/intent/chat-ui-evoflow.md](../intent/chat-ui-evoflow.md)
- 原始需求：[docs/requirements/b35d20344be5cbe62cafffbd445056dd.jpg](../requirements/b35d20344be5cbe62cafffbd445056dd.jpg)（EvoFlow v1.0.3 截图）

## 背景

现有聊天页（[ChatView.vue](../../frontend/src/views/ChatView.vue)）已具备全部数据链路：SSE 事件 `token/tool_start/tool_end/plan/interrupt/error/done`（[chat.js](../../frontend/src/api/chat.js)）驱动 [MessageBubble.vue](../../frontend/src/components/MessageBubble.vue) 内联渲染 PlanPanel（任务计划）+ ToolSteps（工具步骤）。但视觉形态与 EvoFlow 差距大：任务清单是朴素列表、工具日志是折叠卡片、顶部有冗余的「任务清单」按钮+侧板、输入区无功能位、无会话标题栏。

本次为**视觉/交互形态改版**，后端仅新增一个文件上传接口。

## 目标 / 非目标

**目标**
1. 消息流执行过程呈现 EvoFlow 风格：任务清单带勾选与进度、工具执行带状态徽章与终端风输出、思考态折叠
2. 输入区功能位：「+」上传文件进 agent 工作区；「深度思考」可切换占位
3. 顶部会话标题栏（标题 + 运行状态），移除「任务清单」按钮与侧板
4. 整体观感统一（留白、圆角卡片、亮/暗主题）

**非目标**
- EvoFlow 产品级导航（任务中心/工作流/员工等）
- 深度思考的真实模型能力（仅占位，请求不携带任何字段）
- 会话级选模型（另行立项，见 intent 挂起项）
- SSE 协议变更、后端 agent 行为变更

## 现状事实（spec 依据）

| 事实 | 位置 |
|---|---|
| SSE 事件：`token/tool_start/tool_end/plan/interrupt/error/done` | [chat.js:30-41](../../frontend/src/api/chat.js#L30-L41) |
| 事件→消息转换：`onToolStart/onToolEnd→steps`、`onPlan→plan` | [ChatView.vue:266-335](../../frontend/src/views/ChatView.vue#L266-L335) |
| MessageBubble 已内联 PlanPanel + ToolSteps | [MessageBubble.vue:5-8](../../frontend/src/components/MessageBubble.vue#L5-L8) |
| 顶部「任务清单」按钮 + task-panel aside（与消息内 plan 冗余） | [ChatView.vue:21-24, 90-106](../../frontend/src/views/ChatView.vue#L21-L24) |
| agent 工作区：全局单目录 `backend/workspace`（FilesystemBackend, virtual_mode） | [deep_agent.py:125-129](../../backend/agent/deep_agent.py#L125-L129) |
| 后端无对话级文件上传接口（仅 KB uploads） | main.py 无 upload 端点 |
| 主题变量：--bg/--panel/--border/--text/--muted/--accent/--success/--warning/--destructive/--code-bg/--mono；暗色双入口（media query + data-theme）需同步 | style.css（记忆约定） |

## 能力拆解

### C1 消息流执行过程视觉重做（纯前端）

**C1.1 PlanPanel → EvoFlow 任务清单**
- 卡片带标题栏「任务清单」+ 进度条（done/total），进行中项高亮 ▶ 动画，完成项 ✓ + 删除线
- 每项可点击勾选？**否**——plan 由 agent 的 write_todos 驱动，用户勾选不改 agent 状态（避免假交互）；勾选样式仅展示
- 空清单不渲染（现状保持）

**C1.2 ToolSteps → EvoFlow 命令日志**
- 步骤头：状态图标（运行中 ⟳ 动画 / 完成 ✓）+ 工具名等宽字体徽章 + 状态文字 + 折叠箭头（替代文字「详情/收起」）
- 输出区终端风格：深色 code 块（--code-bg）、等宽字体、滚动
- 保持可折叠交互与无障碍属性（aria-expanded）

**C1.3 思考态**：保持现有 typing 三点动画，样式对齐新卡片语言（不新增后端事件）

### C2 顶部标题栏 + 任务面板移除

- chat-head 改为标题栏：左侧当前会话标题（无标题时「新对话」）+ Running 状态徽章（streaming 时显示动画点）；右侧保留 Agent 选择器（样式融入标题栏）
- 移除「任务清单」按钮、`showTasks`/`task-panel` aside 及相关样式（数据已内联，见 C1）
- 移除后确认无残留引用

### C3 输入区改版

**C3.1 「+」文件上传（新后端接口）**

契约（Contract First）：

```
POST /api/chat/upload
Auth: require_admin（沿用现有鉴权依赖）
Content-Type: multipart/form-data，字段 file
成功 200: {"name": "<安全化文件名>", "path": "uploads/<安全化文件名>", "size": <bytes>}
  - 保存至 backend/workspace/uploads/（目录自动创建）；同名覆盖前加时间戳后缀
错误 400: 未选文件 / 超上限（20MB）/ 文件名不安全
错误 401: 未登录
```

- 前端：composer 左侧「+」按钮 → 触发文件选择 → 上传成功后在输入框顶部显示已上传文件 chip（名称+大小+可移除），发送时把「（随消息附带工作区文件：uploads/xxx）」注入消息文本末尾——agent 经 read_file 可读（实施：上传调用放在 ChatView 内，单调用点不抽 api 模块）
- chip 列表仅在待发送期间存在，发送后清空

**C3.2 「深度思考」占位 pill**
- textarea 下方/左侧 pill 按钮，可切换高亮态；悬停 tooltip「即将上线」；不随请求发送任何字段
- 代码中注释标明占位性质，防止后续误认为已接模型

**C3.3 composer 布局**：EvoFlow 式大圆角输入卡：左「+」、中部 textarea（保持 3 行起自适应）、右发送/停止；HITL 禁用逻辑保持

### C4 观感统一

- ThreadList 会话项：当前选中态、时间戳排版微调，对齐新卡片语言
- 全部新样式使用现有主题变量；**暗色双入口必须同步**（style.css media query + data-theme 两处，项目已知约定）
- 不引入新依赖、不引入 EvoFlow 配色

## 测试与验收

| 层 | 方式 |
|---|---|
| 上传接口 | TDD（pytest）：成功保存至 workspace/uploads、400 各分支、401、文件名安全化（路径穿越拦截） |
| 前端构建 | `npm run build` 通过 |
| 视觉/交互 | 浏览器实测：任务清单/工具日志新样式、标题栏 Running 态、+ 上传→chip→发送注入、深度思考切换、HITL 不回退、亮/暗主题 |
| 回归 | 发送/停止/重试/会话切换/引用 badge/KB 评测不受影响 |

## 验收标准（整体）

1. 发消息触发工具调用时，对话流内可见任务清单进度与工具执行日志（EvoFlow 风格），顶部无「任务清单」按钮
2. 「+」上传文件后发送消息，agent 能读到该文件内容（冒烟：上传 txt → 让 agent 报告其内容）
3. 「深度思考」可切换但请求体不含新字段；`npm run build` 与 pytest 全绿

## 补充说明（2026-10-18）

- 需求图（docs/requirements/b35d20344be5cbe62cafffbd445056dd.jpg）对齐补齐：会话条目右侧显示相对时间（刚刚/Xm/Xh/Xd/超一周显示日期，hover 显示绝对时间），数据源为 /api/threads 既有 updated_at（checkpoint created_at）。纯前端，ThreadList.vue 单文件。
- 需求图对齐补齐②：会话列表按 最近活动 分组显示小节标题（今天/昨天/7 天内/更早），组内倒序；纯前端 ThreadList.vue。
- 需求图对齐补齐③：聊天页左侧栏底部新增用户区（头像/用户名/角色 + 主题切换 + 退出）；聊天页顶栏隐藏主题按钮与用户菜单避免重复，其他页面顶栏保持原样。涉及 ThreadList.vue 与 App.vue。
