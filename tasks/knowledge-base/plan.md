# 知识库功能完善 · 实施计划

> spec: [docs/specs/SPEC-knowledge-base.md](../docs/specs/SPEC-knowledge-base.md) · intent: [docs/intent/knowledge-base.md](../docs/intent/knowledge-base.md)

## 策略

自底向上四层，垂直切片：每层「后端 API + 测试 → 前端 UI」为一个可验证切片，层内先 TDD 后实现。
每 2–3 个任务设 Checkpoint：测试全绿 + 前端 HMR 干净 + 人工冒烟。

## 任务顺序与依赖

```
T1 环境冒烟 ──► T2 文档API ──► T3 文档UI ──► CP1
                                T4 检索score/参数 ──► T5 检索预览UI ──► CP2
                                T6 kb_ids绑定 ──► T7 挂载UI ──► T8 引用来源 ──► CP3
                                T9 端到端 + review
```

## 风险

- Qdrant local 模式若与 sparse 模型不兼容，退回 Docker remote 方案（T1 决定）。
- kb 工具闭包绑定涉及 deep_agent 构建链，注意 AGENT_CACHE 热重建回归（已有 test_agent_cache_invalidation 护住）。
- 前端 KnowledgeBase.vue 刚重构过（列表页+模态窗），L2/L3 的 UI 改动在工作区态内做，不动列表态结构。
