# AGENTS.md — 项目工作流约定

本文件定义 AI agent 在本项目中必须遵循的工作流程与文档约定。所有 agent 会话（Claude Code、Cursor、Copilot 等）均应遵守。

**Read CONSTRAINTS.md before writing code. Do not weaken it to make a change pass.**

## 工作流总览

按 agent-skills 的生命周期执行，每个阶段有人工评审门禁，未获确认不得进入下一阶段：

```
DEFINE（需求定义）
  ├─ 需求模糊 → interview-me（一次一问，澄清至 ~95% 置信度）
  ├─ 仅为想法 → idea-refine（发散收敛，产出想法一页纸）
  └─ 意图明确 → spec-driven-development
PLAN（规划）→ planning-and-task-breakdown
BUILD（实施）→ incremental-implementation + test-driven-development
VERIFY（验证）→ debugging-and-error-recovery
REVIEW（审查）→ code-review-and-quality
SHIP（发布）→ shipping-and-launch
```

- Bug 修复不走完整生命周期：问题描述落 `bugs/<bug-name>/bug.md`，按「Bug 修复规范」直接进入 诊断 → 修复 → 验证

## 需求输入与澄清产物（DEFINE 阶段）

- 原始需求文档（PRD、会议纪要、客户邮件、工单等外部输入）：保存到 `docs/requirements/<topic>.md`，作为 DEFINE 阶段的起点
- **原始需求只归档不改写**：需求理解变化时体现在 intent/spec 中，不修改原始文档（确需补充时在文末追加"补充说明"并注明日期）
- `interview-me` 产出的意图声明：经用户**明确确认**后保存到 `docs/intent/<topic>.md`
- `idea-refine` 产出的一页纸（Problem / Direction / Assumptions / MVP / Not Doing）：经确认后保存到 `docs/ideas/<idea-name>.md`
- **未经用户确认，禁止落盘任何文档**
- 这些文档是 spec 的输入，不是流程终点

## Spec 规范（spec-driven-development）

- 大需求先产出**能力地图**（模块表 + 依赖方向 + 构建顺序），经用户评审后才写各模块 spec
- spec 的背景节链接对应的原始需求文档（`docs/requirements/...`），形成 需求 → spec → PR 的追溯链
- 模块 id 使用 kebab-case，一旦确定不改名
- 逐模块递归执行 Specify → Plan → Tasks → Implement
- 接口契约遵循 Contract First，设计规范使用 `api-and-interface-design`；模块间契约写入**提供方模块**的 spec
- 架构选型决策（框架、数据库、消息中间件等）同步用 `documentation-and-adrs` 记录 ADR，记录"为什么"，包括被否掉的备选方案

### 文档存放位置（本项目的覆盖约定）

```
docs/
├── MCP_GUIDE.md                    ← MCP 接入与使用指南（配置/身份越界闸/后台可视化管理/验证步骤）
├── requirements/
│   └── <topic>.md                 ← 原始需求文档（PRD/纪要/邮件等，只归档不改写）
├── project-map.md                 ← 存量总览：模块地图 + 数据模型（表关系/字段语义/枚举，结构指向代码不复制）
├── api/
│   ├── openapi.yaml               ← REST 接口契约（OpenAPI）
│   └── <module>.md                ← 非标接口的契约说明
├── specs/
│   ├── CAPABILITY-MAP.md          ← 全局能力地图（跨功能共享，作为模块索引）
│   ├── SPEC-<module-id>.md        ← 各模块/功能 spec，按 module-id 命名
│   └── SPEC.md                    ← 单能力小需求可直接用此名
├── intent/<topic>.md              ← interview-me 意图声明
├── ideas/<idea-name>.md           ← idea-refine 想法一页纸
└── adr/
    ├── ADR-001-xxx.md             ← 架构决策记录，顺序编号，沿用现有序号
    └── ADR-002-xxx.md
```

- ADR 只增不改：决策变更时写新 ADR 并标记旧的为 Superseded，**不删除旧记录**

## 存量项目文档（Brownfield）

存量系统的"设计/架构/接口"文档按以下方式生成与存放，**不为存量代码补写 spec**：

- **架构与数据模型现状**：用 `context-engineering` 生成 Project Map 存 `docs/project-map.md`（模块地图 + 数据模型一节：表关系、字段业务语义、枚举含义；表结构本身指向 migrations/schema 不复制；代码推导不出的语义列清单问人，不编造），本文件只留一行索引；小项目直接并入本文件的 Project Map 节
- **历史决策**：用 `documentation-and-adrs` 回溯补记**重大且有争议余地**的选型 ADR 到 `docs/adr/`；理由已不可考时如实写"不可考 + 推测"，不编造；Date 写补记日期
- **接口契约**：新代码对接老模块前，用 `api-and-interface-design` 先定契约；REST 接口用 OpenAPI 存 `docs/api/`，能用类型内联表达的优先内联在代码里
- **现状行为**：用 `test-driven-development` 补**特征测试**钉住（对错都先钉），只覆盖将要改动的区域；发现疑似 bug 停下来问人，不默默钉成期望行为
- **红线**：改存量代码前必须有特征测试网（No characterization tests, no refactor）

## 任务规范（planning-and-task-breakdown）

- **按功能隔离任务目录**，每个功能/initiative 一套，支持并行开发：

```
tasks/
├── <feature-name>/
│   ├── plan.md                    ← 该功能的实施计划
│   └── todo.md                    ← 该功能的任务清单
```

- 新功能启动时先建 spec（评审通过），再创建对应 `tasks/<feature-name>/`
- **禁止覆盖未完成的计划**：写入 plan/todo 前检查目标文件是否还有未勾选任务；属于不同工作则停下来询问用户
- 任务尺寸：S（1–2 文件）/ M（3–5 文件）为宜；L（5–8）必须再拆；XL（8+）禁止
- 拆分采用**垂直切片**（一个完整用户路径一个任务），不做水平分层（先全部 DB 再全部 API 再全部 UI）
- 每个任务必须包含：验收标准（≤3 条）、验证步骤（测试/构建/手动检查）、依赖关系、涉及文件
- 任务清单按 Phase 分组，每 2–3 个任务设一个 Checkpoint（测试通过、构建干净、核心流程可用、需人工确认后再继续）

## Bug 修复规范（debugging-and-error-recovery）

- **按 bug 隔离目录**，与 `tasks/` 平行，每个 bug 一套：

```
bugs/
├── <bug-name>/
│   ├── bug.md          ← 问题描述（现象、复现步骤、日志/截图证据；只归档不改写）
│   ├── todo.md         ← 修复清单，按诊断步骤逐项勾选并就地记录
│   └── fix.md          ← 修复记录：根因、改动范围、回归测试、验证结果
```

- `<bug-name>` 使用 kebab-case；一行可修的小问题允许合并为单文件 `bugs/<bug-name>.md`（描述与记录合一）
- 流程：问题描述写入 `bug.md` → 调用 `debugging-and-error-recovery`，按诊断步骤（复现 → 定位 → 最小化 → 修根因 → 补回归测试 → 端到端验证）生成 `todo.md` 并逐项执行
- 回归测试遵循 `test-driven-development`：先写失败测试再修复，**没有回归测试不得勾选完成**
- 复现不了的 bug：把已排查的环境/条件差异记录进 `todo.md`，加监控告警后挂起，不凭猜测修复
- 调试中发现的其他问题**另建 bug 目录**，不混入当前修复（避免污染修复范围）
- 跨模块/架构级 bug 升级为 spec，走 DEFINE 完整流程；修复完成后填写 `fix.md`

## 实施规范（BUILD）

- 一次执行一个任务，完成后立即勾选并验证
- TDD：先写失败的测试，再实现，再重构（red-green-refactor）
- 框架/库用法拿不准时，用 `source-driven-development` 对照官方文档，不凭记忆写 API
- 高风险/不可逆操作前，用 `doubt-driven-development` 做对抗性审查

## Boundaries

- **Always**: 提交前跑测试；遵循本文件的命名与目录约定；在系统边界校验外部输入
- **Ask first**: 新增依赖、数据库 schema 变更、修改 CI 配置、覆盖未完成的计划文件
- **Never**: 提交 secrets；未经 spec 评审直接开始实现；删除旧 ADR；注释掉代码代替删除

## 提交与 PR

- 提交遵循 `git-workflow-and-versioning`
- PR 描述中链接回所实现的 spec 章节（`docs/specs/SPEC-<module-id>.md#章节`）；bug 修复 PR 链接回修复记录（`bugs/<bug-name>/fix.md`）
- spec 是唯一事实来源：需求或决策变更时，**先改 spec / 写新 ADR，再改代码**