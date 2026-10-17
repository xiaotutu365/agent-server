"""暴露给 deep agent 的知识库检索工具。

make_kb_tools(kb_ids) 按 agent 挂载的库列表生成工具实例（闭包绑定）：
- kb_ids=[]：旧行为，可检索任意库（kb_id 由 LLM 指定，缺省 "default"）
- kb_ids 非空：未指定 kb_id 时跨挂载库检索并按 score 合并；指定挂载外的库则拒绝

工具返回 JSON 字符串（LLM 可读，SSE tool_end 侧可解析 citations）：
{"results": [{content, kb_id, source, chunk_idx, score}]} 或 {"error": "..."}
"""

import json as _json

from langchain_core.tools import tool

import kb.config as cfg
import kb.embed as embed
from kb import retrieval


def _search(kb_id: str, query: str, top_k: int):
    """单库检索；返回 (docs, error)。"""
    try:
        cfg.validate_kb_id(kb_id)
    except ValueError as e:
        return None, str(e)
    try:
        docs = retrieval.hybrid_search(kb_id, query, top_k=top_k)
    except embed.EmbeddingUnavailable as e:
        return None, str(e)
    except Exception as exc:  # noqa: BLE001
        return None, f"知识库检索失败: {exc}"
    return docs, None


def make_kb_tools(kb_ids: list):
    allowed = [k for k in (kb_ids or []) if k]

    @tool
    def search_knowledge_base(query: str, kb_id: str = "", top_k: int = 5) -> str:
        """从知识库检索与问题相关的文档片段。

        当用户问到内部制度、产品文档、FAQ、历史资料等不在联网范围的知识时调用。
        kb_id 一般无需填写（默认检索已挂载的全部知识库并按相关性合并）。
        返回 JSON：{"results": [{content, kb_id, source, chunk_idx, score}]}，
        引用回答时注明来源文件与片段号。
        """
        if kb_id:
            if allowed and kb_id not in allowed:
                return _json.dumps(
                    {"error": f"未挂载知识库 {kb_id}，可用: {', '.join(allowed)}"},
                    ensure_ascii=False,
                )
            targets = [kb_id]
        else:
            targets = allowed or ["default"]
        if not targets:
            return _json.dumps({"error": "未挂载任何知识库。"}, ensure_ascii=False)

        all_docs, last_err = [], None
        for t in targets:
            docs, err = _search(t, query, top_k)
            if err:
                last_err = err
                continue
            all_docs.extend(docs)
        if not all_docs:
            return last_err or _json.dumps({"results": []}, ensure_ascii=False)
        all_docs.sort(key=lambda d: d.metadata.get("score") or 0, reverse=True)
        return _json.dumps(
            {
                "results": [
                    {
                        "content": d.page_content,
                        "kb_id": d.metadata.get("kb_id", ""),
                        "source": d.metadata.get("source", "?"),
                        "chunk_idx": d.metadata.get("chunk_idx", 0),
                        "score": d.metadata.get("score"),
                    }
                    for d in all_docs[:top_k]
                ]
            },
            ensure_ascii=False,
        )

    return [search_knowledge_base]


# 全局注册表用（工具目录页展示）：全库行为
KB_TOOLS = make_kb_tools([])
