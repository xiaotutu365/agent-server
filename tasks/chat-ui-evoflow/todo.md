# TODO：聊天窗口 EvoFlow 风格改版

## T1 上传接口（S）
- [x] 写失败测试 tests/test_chat_upload.py（成功/400 三分支/401/文件名安全化）
- [x] main.py 实现 POST /api/chat/upload（require_admin、20MB 上限、workspace/uploads/、同名时间戳）
- [x] pytest 全绿 【CP1】6/6 用例过，全量 145 passed；curl 冒烟通过（重名→时间戳后缀）

## T2 消息流组件重做（M）
- [x] PlanPanel：标题栏+进度条+勾选样式+进行中动画
- [x] ToolSteps：状态徽章+折叠箭头+终端风输出
- [x] typing 态样式对齐（保持三点动画，卡片语言统一）

## T3 标题栏（M）
- [x] chat-head → 会话标题 + Running 徽章 + Agent 选择器融入
- [x] 移除「任务清单」按钮、showTasks/task-panel 及样式，确认无残留引用（watch import 一并清理）

## T4 composer（M）
- [x] POST /api/chat/upload 前端调用（ChatView 内 apiFetch FormData，无新依赖）
- [x] 「+」按钮 → 文件选择 → 上传 → chip 列表（可移除）+ 错误提示行
- [x] 发送时消息注入「（随消息附带工作区文件：uploads/…）」，发送后清空
- [x] 「深度思考」pill 占位（tooltip 即将上线，不发送字段，代码注释标明）
- [x] HITL/停止/发送禁用逻辑保持（canSend 兼许仅文件发送）【CP2】npm run build 过；浏览器 7 项 PASS

## T5 收尾（S）
- [x] ThreadList 选中态/排版微调（accent 淡背景 + 加粗）
- [x] 新样式全部使用现有主题变量 + color-mix，无新增变量，暗色双入口无需改动（浏览器实测暗色无白块）
- [x] npm run build + pytest 全量 145 passed
- [x] 浏览器实测：上传→agent read_file 读到 Phoenix 冒烟、亮/暗主题、无控制台报错 【CP3】

## 记录
- 空字符串 filename 的 multipart 会被 Starlette 以 422 拒绝（真实浏览器不会发空文件名），测试改用全空白名验证 400 分支
- agent 工具相对路径从 workspace 根起步，消息注入用 `uploads/xxx`（非 `workspace/uploads/xxx`）
- 上传接口用 20MB 限制时先 read(MAX+1) 再判长度，避免超限文件先落盘
- 发送按钮 canSend 扩展为「有文本或有待发文件」，仅上传文件不输文字也可发送
