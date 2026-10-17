# Intent: 知识库分片策略（kb-chunking-strategy）

> interview-me 产出，用户已明确确认（2026-10-17）。

## 背景与问题

当前知识库上传文档时，分片方式写死为固定长度+重叠（`RecursiveCharacterTextSplitter`，chunk_size=800 / overlap=100）。不同类型的文档（长文档、Markdown 结构化文档、FAQ 问答对）只能用同一种切法，无法选择合适的分片策略。

## 目标

在知识库「设置」面板（**全局一处**，与 top_k/rerank 同区）新增**分片策略**选择，三种预设：

1. **固定长度 + 重叠**（默认，即当前行为）——通用兜底
2. **按段落/标题切**——保 Markdown/结构化文档语义完整
3. **按空行分段**——适合 FAQ、问答对等天然分条内容

## 成功标准

- 切换策略并保存后，新上传的文档按所选策略分片（片段数/边界符合策略预期）
- 配置持久化；pytest 全绿 + 前端冒烟通过

## 约束

- 全局一处设置，所有库统一
- **不自动重建**：新策略仅对之后上传的文档生效，旧文档需删除重传；改策略时 UI 提示「仅对新上传生效」

## 明确不做（Out of scope）

- 高级参数数值可调（chunk size / overlap / 自定义分隔符）——后续加
- 每库独立策略、上传时逐次选择
- 一键重建全库
- 语义切分（embedding 相似度切分）

## 补充说明（用户 2026-10-17）

- 业界参照：LlamaIndex 的 node parsers 是 RAG 切分的流行方案
- 决策：不引入 llama-index-core（新重依赖），直接用**依赖树里已有的 `langchain-text-splitters`**（deepagents → langchain 自带）实现三种策略；语义对齐 LlamaIndex（TokenTextSplitter / MarkdownNodeParser / 分隔符模式），为后续演进留路径
