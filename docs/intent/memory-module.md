# 意图声明：DeepAgent 记忆模块（参照 RAGFlow Memory）

- 确认时间：2026-10-17
- 确认方式：interview-me 四问确认（分类范围/存储/归属与时机/UI）

## Outcome

DeepAgent 长期记忆能力，参照 RAGFlow Memory 模块设计：

1. **自动抽取**：每轮对话结束后，后台用当前对话模型从该轮对话中抽取 Semantic 记忆（关于用户偏好/事实/项目背景的陈述句），失败静默跳过，不阻塞回复流
2. **检索注入**：每轮对话开始前，按用户当前消息向量检索 top-5 相关记忆，拼进 system prompt（标注"以下是关于该用户的已知记忆，供参考"）
3. **管理页**：管理后台新增「记忆」页——条目列表（内容/创建时间/来源 thread）、启用/停用、手动遗忘（删除）、手动添加

## User / Why now

- 用户：管理员（管理页），所有聊天用户（自动受益）
- 动机：现有 thread 持久化只跨轮不跨会话，Agent 不记得用户；RAGFlow 四分类设计提供了成熟蓝本

## Success

- 聊一轮后管理页出现抽取的记忆条目
- 新开会话问相关问题，回答体现记忆内容

## Constraint

- 第一期只做 **Semantic** 类（schema 预留 memory_type 字段，二期扩 Episodic/Procedural）
- **零新依赖**：SQLite 存元数据（memories 表，复用 agent 库）、Qdrant 独立 collection `memories` 存向量（与知识库隔离）、embedding 复用 kb 已配置的智谱 embedding-3
- 记忆按 **user_id 隔离**，跨 thread / 跨 Agent 生效（记住"人"而非会话）
- 抽取异步 fire-and-forget

## Out of scope

- Episodic / Procedural / Raw 记忆分类（Raw 对话已有 thread 持久化）
- Agent 级记忆、团队共享、容量自动遗忘策略
- 聊天页记忆显式展示 UI

## 对应实现蓝图（RAGFlow 术语 → 本项目）

- Message 组件"Save to Memory" → chat 流 done 后异步抽取入库
- Retrieval 组件"Retrieve from memory" → 对话前向量检索注入 system prompt
- Memory 配置（embedding 模型）→ 复用 kb settings 的 embedding 配置
- 遗忘 → enabled=false（软停用）与 DELETE（硬遗忘）
