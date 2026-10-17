# 知识库检索调优（向量权重 + 相似度阈值）

意图：docs/intent/kb-retrieval-tuning.md（2026-10-17 已确认）
Spec：SPEC-knowledge-base.md 能力 L8

## Phase 1 后端（TDD）

- [x] T1 失败测试：加权 RRF（w=1 纯 dense 序 / w=0 纯 sparse 序 / w=0.5 回归一致）+ 阈值过滤（cosine 低于阈值滤除 / 纯 sparse 保留 / threshold=0 不过滤）+ 运行时覆盖（tests/test_kb_retrieval_tuning.py，14 用例）
- [x] T2 失败测试：save_settings 非法 vector_weight（越界/非数值）/ 负 threshold → ValueError；API 层 400
- [x] T3 settings.py：DEFAULTS 增 vector_weight=0.5、similarity_threshold=0.0 + 数值校验（通过校验后归一为 float 落盘）
- [x] T4 retrieval.py：_rrf 加权（weights 参数）+ dense cosine 映射保留 + _maybe_rerank 返回 (ranked, rerank_scores) + _apply_threshold（rerank 分优先 → cosine 分，纯 sparse 保留）+ hybrid_search/hybrid_search_ex 签名扩展；14 用例转绿

## Phase 2 前端

- [x] T5 KnowledgeBase.vue 检索设置区：向量权重滑条（0~1 步长 0.05，label 实时显示当前值）+ 相似度阈值数字输入 + RAGFlow 式提示文案；settingsForm 默认值补 2 字段（加载/保存按表单 key 遍历，自动进出）

## Phase 3 验证与收尾

- [x] T6 pytest 全量 137 passed（无回归）+ npm run build 通过
- [x] T7 SPEC L8 节 + intent + tasks 已落盘；代码未提交（与后续工作一起提交）

## 发现与决策记录

- `_maybe_rerank` 原实现吞异常返回原序——新增 rerank_scores 返回值时曾因 `hits[i].id`（hits 元素是 (hit, score) 元组）抛 AttributeError 被吞，改为 `hits[i][0].id`；提示：该函数 except 兜底宽，改动后靠端到端测试钉住行为
- 阈值过滤置于 rerank 之后、截断 top_k 之前：先过滤后截断保证 top_k 名额给达标片段
- 展示分保持 RRF 融合分不变（引用 badge / 评测页显示不受影响），rerank 分只用于过滤与排序
- API 层 /api/kb/settings GET/PUT 为 dict 透传 + ValueError→400 已有映射，新字段零改动自动生效
