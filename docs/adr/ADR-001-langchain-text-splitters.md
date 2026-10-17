# ADR-001: 知识库分片策略用 langchain-text-splitters 实现

- **状态**: Accepted
- **日期**: 2026-10-17
- **关联**: [SPEC-knowledge-base.md 能力 L5](../specs/SPEC-knowledge-base.md)、[intent/kb-chunking-strategy.md](../intent/kb-chunking-strategy.md)

## 背景

知识库分片策略需要从写死的「固定长度+重叠」扩展为三种可配预设（fixed / markdown / blank_line）。需要一个切分实现，业界流行参照是 LlamaIndex 的 node parsers。

## 决策

直接使用项目依赖树中**已有的** `langchain-text-splitters`（deepagents → langchain 自带，零新增依赖）：

- `fixed` → `RecursiveCharacterTextSplitter`（现行为）
- `markdown` → `MarkdownHeaderTextSplitter`（按标题层级）
- `blank_line` → 按 `\n\n` 分段 + 超长兜底切

命名与行为语义对齐 LlamaIndex（`TokenTextSplitter` / `MarkdownNodeParser` / 分隔符模式），为后续引入语义切分留清晰演进路径。

## 被否掉的备选方案

1. **引入 llama-index-core**：整个框架围绕 RAG 设计、node parsers 最全，但只为三个切分函数引入一串重依赖，且与现有 langchain/deepagents 栈并存增加心智负担——否。
2. **自己手写切分逻辑**：边界情况（标题层级、超长兜底）重复造轮子，无社区测试兜底——否。

## 后果

- 零新增依赖，切分行为有 langchain 社区维护与测试兜底
- 高级参数（自定义分隔符、数值可调）后续在同一抽象上扩展
