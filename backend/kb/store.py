"""Qdrant 向量库连接与集合管理（每知识库一个 collection，双向量）。"""

from qdrant_client import QdrantClient, models

import kb.config as cfg
import kb.settings as settings


_client = None


def get_client() -> QdrantClient:
    """返回（惰性创建）全局 Qdrant 客户端。

    优先使用本地嵌入式模式（QDRANT_LOCAL_PATH 非空），无需 Docker 即可运行；
    设为空字符串则改为连接 QDRANT_URL（Docker / 云 Qdrant）。
    """
    global _client
    if _client is None:
        try:
            if cfg.QDRANT_LOCAL_PATH:
                _client = QdrantClient(path=cfg.QDRANT_LOCAL_PATH)
            else:
                _client = QdrantClient(
                    url=cfg.QDRANT_URL, api_key=cfg.QDRANT_API_KEY or None
                )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"无法连接 Qdrant：{exc}。"
                "本地模式请检查 QDRANT_LOCAL_PATH；Docker 模式请先启动："
                "docker run -d -p 6333:6333 qdrant/qdrant"
            ) from exc
    return _client


def _vectors_config():
    return {
        cfg.DENSE_NAME: models.VectorParams(
            size=settings.get_settings()["embedding_dim"], distance=models.Distance.COSINE
        )
    }


def _sparse_config():
    return {cfg.SPARSE_NAME: models.SparseVectorParams()}


def create_kb(kb_id: str, description: str = "") -> dict:
    """创建知识库（collection）。已存在则直接返回。"""
    name = cfg.collection_name(kb_id)
    client = get_client()
    if client.collection_exists(collection_name=name):
        return {"kb_id": kb_id, "status": "exists"}
    client.create_collection(
        collection_name=name,
        vectors_config=_vectors_config(),
        sparse_vectors_config=_sparse_config(),
    )
    if description:
        client.update_collection(
            collection_name=name,
            hnsw_config=models.HnswConfigDiff(),
        )
    return {"kb_id": kb_id, "status": "created"}


def drop_kb(kb_id: str) -> dict:
    """删除知识库（整个 collection）。"""
    name = cfg.collection_name(kb_id)
    client = get_client()
    if not client.collection_exists(collection_name=name):
        return {"kb_id": kb_id, "status": "not_found"}
    client.delete_collection(collection_name=name)
    return {"kb_id": kb_id, "status": "deleted"}


def list_kbs() -> list:
    """列出所有知识库（以 kb_ 前缀识别）。"""
    client = get_client()
    collections = client.get_collections().collections
    result = []
    for c in collections:
        if c.name.startswith("kb_"):
            info = client.get_collection(collection_name=c.name)
            result.append({
                "kb_id": c.name[len("kb_"):],
                "points_count": getattr(info, "points_count", 0) or 0,
                "status": str(getattr(info, "status", "")),
            })
    return result


def upsert_points(kb_id: str, points: list) -> int:
    """批量写入点（points 为 qdrant PointStruct 列表）。"""
    if not points:
        return 0
    client = get_client()
    name = cfg.collection_name(kb_id)
    if not client.collection_exists(collection_name=name):
        create_kb(kb_id)
    client.upsert(collection_name=name, points=points)
    return len(points)


def kb_exists(kb_id: str) -> bool:
    return get_client().collection_exists(collection_name=cfg.collection_name(kb_id))


def _source_filter(source: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))])


def list_documents(kb_id: str) -> list:
    """按 source 聚合列出库内文档：[{file, chunks, size_chars}]。库不存在返回 None。"""
    client = get_client()
    name = cfg.collection_name(kb_id)
    if not client.collection_exists(collection_name=name):
        return None
    agg: dict = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=name,
            with_payload=["source", "text"],
            limit=256,
            offset=offset,
        )
        for p in points:
            source = (p.payload or {}).get("source") or "未知来源"
            text = (p.payload or {}).get("text") or ""
            a = agg.setdefault(source, {"file": source, "chunks": 0, "size_chars": 0})
            a["chunks"] += 1
            a["size_chars"] += len(text)
        if offset is None:
            break
    return sorted(agg.values(), key=lambda d: d["file"])


def get_chunk(kb_id: str, source: str, chunk_idx: int) -> dict | None:
    """按 (source, chunk_idx) 精确取一个片段的 payload；库/片段不存在返回 None。"""
    client = get_client()
    name = cfg.collection_name(kb_id)
    if not client.collection_exists(collection_name=name):
        return None
    flt = models.Filter(must=[
        models.FieldCondition(key="source", match=models.MatchValue(value=source)),
        models.FieldCondition(key="chunk_idx", match=models.MatchValue(value=chunk_idx)),
    ])
    points, _ = client.scroll(
        collection_name=name, scroll_filter=flt, with_payload=True, limit=1,
    )
    if not points:
        return None
    payload = points[0].payload or {}
    return {
        "kb_id": kb_id,
        "source": payload.get("source") or source,
        "chunk_idx": payload.get("chunk_idx", chunk_idx),
        "text": payload.get("text") or "",
    }


def delete_document(kb_id: str, source: str) -> dict:
    """删除单个文档（按 payload source 过滤）。返回 deleted 数；库/文档不存在返回 not_found。"""
    client = get_client()
    name = cfg.collection_name(kb_id)
    if not client.collection_exists(collection_name=name):
        return {"status": "not_found", "deleted": 0}
    flt = _source_filter(source)
    count = client.count(collection_name=name, count_filter=flt, exact=True).count
    if count == 0:
        return {"status": "not_found", "deleted": 0}
    client.delete(collection_name=name, points_selector=models.FilterSelector(filter=flt))
    return {"status": "deleted", "deleted": count}
