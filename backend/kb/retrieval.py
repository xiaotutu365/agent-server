"""混合检索：dense 向量 + BM25 稀疏向量，RRF 融合；封装为 langchain Retriever。"""

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

import kb.config as cfg
import kb.embed as embed
import kb.settings as settings
from kb import store


def _rrf(result_lists: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion：多个结果列表按排名融合。"""
    fused = {}
    for hits in result_lists:
        for rank, hit in enumerate(hits):
            entry = fused.setdefault(hit.id, {"hit": hit, "score": 0.0})
            entry["score"] += 1.0 / (k + rank + 1)
    ranked = sorted(fused.values(), key=lambda e: e["score"], reverse=True)
    return [e["hit"] for e in ranked]


def hybrid_search(kb_id: str, query: str, top_k: int = None, candidate: int = None) -> list:
    """对指定知识库做混合检索，返回 Document 列表（已按相关性排序）。"""
    s = settings.get_settings()
    top_k = s["top_k"] if top_k is None else top_k
    candidate = s["candidate"] if candidate is None else candidate
    if not store.kb_exists(kb_id):
        return []
    client = store.get_client()
    name = cfg.collection_name(kb_id)
    dense, sparse = embed.embed_query(query)

    dense_hits = client.query_points(
        collection_name=name,
        query=dense, using=cfg.DENSE_NAME,
        limit=candidate, with_payload=True,
    ).points
    sparse_hits = client.query_points(
        collection_name=name,
        query=sparse, using=cfg.SPARSE_NAME,
        limit=candidate, with_payload=True,
    ).points

    fused = _rrf([dense_hits, sparse_hits], k=s["rrf_k"])
    ranked = _maybe_rerank(query, fused)

    docs = []
    for hit in ranked[:top_k]:
        payload = hit.payload or {}
        text = payload.pop("text", "")
        docs.append(Document(page_content=text, metadata=payload))
    return docs


def _maybe_rerank(query: str, hits: list) -> list:
    """若配置了默认「重排(rerank)」模型，则对候选集重排；任何失败都回退 RRF 顺序。

    兼容常见 rerank 接口（Cohere / Jina / Voyage 等）：POST base_url，
    body 为 {model, query, documents}，返回 {results|data:[{index, relevance_score|score}]}。
    """
    try:
        from agent.model_store import get_default_sync

        rm = get_default_sync("rerank")
        if not rm or not rm.get("model"):
            return hits
        import json as _json
        import urllib.request

        docs_text = [(_h.payload or {}).get("text", "") for _h in hits]
        body = _json.dumps(
            {"model": rm["model"], "query": query, "documents": docs_text}
        ).encode("utf-8")
        req = urllib.request.Request(rm["base_url"], data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if rm.get("api_key"):
            req.add_header("Authorization", "Bearer " + rm["api_key"])
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or data.get("data") or []
        scored = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if isinstance(idx, int) and 0 <= idx < len(hits):
                scored.append((idx, score if isinstance(score, (int, float)) else 0.0))
        if not scored:
            return hits
        scored.sort(key=lambda x: x[1], reverse=True)
        return [hits[i] for i, _ in scored]
    except Exception:  # noqa: BLE001
        return hits


class KbRetriever(BaseRetriever):
    """langchain Retriever 适配，便于直接接入链/agent。"""

    kb_id: str
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(self, query: str, run_manager=None) -> list:
        return hybrid_search(self.kb_id, query, top_k=self.top_k)

    async def _aget_relevant_documents(self, query: str, run_manager=None) -> list:
        return hybrid_search(self.kb_id, query, top_k=self.top_k)
