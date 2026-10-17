"""混合检索：dense 向量 + BM25 稀疏向量，RRF 融合；封装为 langchain Retriever。"""

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

import kb.config as cfg
import kb.embed as embed
import kb.settings as settings
from kb import store


def _rrf(result_lists: list, k: int = 60, weights: list = None) -> list:
    """Reciprocal Rank Fusion：多个结果列表按排名融合，返回 [(hit, score)] 按分数降序。

    weights 为每路权重（如混合检索传 [vector_weight, 1-vector_weight]），
    None 时各路等权（现行为）。
    """
    weights = weights or [1.0] * len(result_lists)
    fused = {}
    for w, hits in zip(weights, result_lists):
        for rank, hit in enumerate(hits):
            entry = fused.setdefault(hit.id, {"hit": hit, "score": 0.0})
            entry["score"] += w / (k + rank + 1)
    ranked = sorted(fused.values(), key=lambda e: e["score"], reverse=True)
    return [(e["hit"], e["score"]) for e in ranked]


def _apply_threshold(ranked: list, dense_scores: dict, rerank_scores: dict, threshold: float) -> list:
    """按相似度阈值过滤 [(hit, score)] 列表（rerank 之后、截断 top_k 之前）。

    分数源优先级：rerank relevance_score > dense cosine 分（RRF 分不归一，不可作阈值）。
    - 有 rerank 分：缺失分数视为 0（不达标）
    - 无 rerank：按 dense cosine 分过滤；纯 sparse 召回（无 cosine 分）的片段保留不误杀
    - threshold <= 0：不过滤（现行为）
    """
    if threshold is None or threshold <= 0:
        return ranked
    if rerank_scores:
        return [(h, s) for h, s in ranked if rerank_scores.get(h.id, 0.0) >= threshold]
    return [(h, s) for h, s in ranked
            if h.id not in dense_scores or dense_scores[h.id] >= threshold]


def hybrid_search_ex(
    kb_id: str,
    query: str,
    top_k: int = None,
    candidate: int = None,
    rrf_k: int = None,
    vector_weight: float = None,
    similarity_threshold: float = None,
) -> tuple:
    """同 hybrid_search，另返回降级原因（空串=正常路径），供 API/工具层即使零结果也提示。"""
    s = settings.get_settings()
    top_k = s["top_k"] if top_k is None else top_k
    candidate = s["candidate"] if candidate is None else candidate
    rrf_k = s["rrf_k"] if rrf_k is None else rrf_k
    vector_weight = s["vector_weight"] if vector_weight is None else vector_weight
    similarity_threshold = (
        s["similarity_threshold"] if similarity_threshold is None else similarity_threshold
    )
    if not store.kb_exists(kb_id):
        return [], ""
    client = store.get_client()
    name = cfg.collection_name(kb_id)

    # dense 向量不可用（未配置 / 网络失败等任何 dense 侧故障）时降级为纯 BM25 并标记
    fallback = ""
    try:
        dense, sparse = embed.embed_query(query)
    except Exception as e:  # noqa: BLE001  # EmbeddingUnavailable / openai 连接错误等一律降级
        fallback = f"embedding 不可用，已降级为关键词检索（{e}）"
        dense, sparse = None, embed.sparse_query(query)

    dense_hits = []
    dense_scores = {}  # hit.id -> dense cosine 分（阈值过滤用；降级时为空即整体跳过）
    if dense is not None:
        dense_hits = client.query_points(
            collection_name=name,
            query=dense, using=cfg.DENSE_NAME,
            limit=candidate, with_payload=True,
        ).points
        dense_scores = {h.id: h.score for h in dense_hits if h.payload}
    sparse_hits = client.query_points(
        collection_name=name,
        query=sparse, using=cfg.SPARSE_NAME,
        limit=candidate, with_payload=True,
    ).points

    fused = _rrf([dense_hits, sparse_hits], k=rrf_k, weights=[vector_weight, 1.0 - vector_weight])
    ranked, rerank_scores = _maybe_rerank(query, fused)
    ranked = _apply_threshold(ranked, dense_scores, rerank_scores, similarity_threshold)

    docs = []
    for hit, score in ranked[:top_k]:
        payload = hit.payload or {}
        text = payload.pop("text", "")
        payload["score"] = score
        if fallback:
            payload["fallback"] = fallback
        docs.append(Document(page_content=text, metadata=payload))
    return docs, fallback


def hybrid_search(
    kb_id: str,
    query: str,
    top_k: int = None,
    candidate: int = None,
    rrf_k: int = None,
    vector_weight: float = None,
    similarity_threshold: float = None,
) -> list:
    """混合检索，返回 Document 列表（保持既有签名；需要降级原因用 hybrid_search_ex）。"""
    return hybrid_search_ex(
        kb_id, query, top_k=top_k, candidate=candidate, rrf_k=rrf_k,
        vector_weight=vector_weight, similarity_threshold=similarity_threshold,
    )[0]


def _maybe_rerank(query: str, hits: list) -> tuple:
    """若配置了默认「重排(rerank)」模型，则对候选集重排；任何失败都回退 RRF 顺序。

    入参为 [(hit, rrf_score)]；返回 (ranked, rerank_scores)：
    - ranked：[(hit, rrf_score)] 重排后列表（展示分保持 RRF 融合分，rerank 只影响顺序）
    - rerank_scores：{hit_id: relevance_score}，供相似度阈值过滤；未配置/失败时为 {}
    兼容常见 rerank 接口（Cohere / Jina / Voyage 等）：POST base_url，
    body 为 {model, query, documents}，返回 {results|data:[{index, relevance_score|score}]}。
    """
    try:
        from agent.model_store import get_default_sync

        rm = get_default_sync("rerank")
        if not rm or not rm.get("model"):
            return hits, {}
        import json as _json
        import urllib.request

        docs_text = [(_h.payload or {}).get("text", "") for _h, _s in hits]
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
            return hits, {}
        scored.sort(key=lambda x: x[1], reverse=True)
        rerank_scores = {hits[i][0].id: s for i, s in scored}
        return [hits[i] for i, _ in scored], rerank_scores
    except Exception:  # noqa: BLE001
        return hits, {}


class KbRetriever(BaseRetriever):
    """langchain Retriever 适配，便于直接接入链/agent。"""

    kb_id: str
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(self, query: str, run_manager=None) -> list:
        return hybrid_search(self.kb_id, query, top_k=self.top_k)

    async def _aget_relevant_documents(self, query: str, run_manager=None) -> list:
        return hybrid_search(self.kb_id, query, top_k=self.top_k)
