"""暴露给 deep agent 的知识库检索工具。"""

from langchain_core.tools import tool

import kb.config as cfg
from kb import retrieval
import kb.embed as embed


@tool
def search_knowledge_base(query: str, kb_id: str = "default", top_k: int = 5) -> str:
    """从指定知识库检索与问题相关的文档片段。

    当用户问到内部制度、产品文档、FAQ、历史资料等不在联网范围的知识时调用。
    kb_id 用于区分不同主题/部门的知识库（如 "policy"、"product"）。
    示例: search_knowledge_base("退货政策", kb_id="policy")
    """
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        return str(e)
    try:
        docs = retrieval.hybrid_search(kb_id, query, top_k=top_k)
    except embed.EmbeddingUnavailable as e:
        return str(e)
    except Exception as exc:  # noqa: BLE001
        return f"知识库检索失败: {exc}"
    if not docs:
        return "未在该知识库中找到相关内容（或知识库不存在）。"
    return "\n\n".join(
        f"[来源: {d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs
    )


KB_TOOLS = [search_knowledge_base]
