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
