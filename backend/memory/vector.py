"""记忆向量检索：Qdrant 独立 collection `memories`（与知识库隔离，dense-only）。

embedding 复用 kb.embed / kb.settings 配置；任何 embedding 侧故障静默返回空，
不影响对话主流程。
"""

from qdrant_client import models

import kb.config as cfg
import kb.embed as embed
import kb.settings as settings
from kb import store

COLLECTION = "memories"


def _client():
    return store.get_client()


def ensure_collection():
    """按当前 kb embedding 维度创建 memories collection（已存在则跳过）。"""
    client = _client()
    if client.collection_exists(collection_name=COLLECTION):
        return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            cfg.DENSE_NAME: models.VectorParams(
                size=settings.get_settings()["embedding_dim"],
                distance=models.Distance.COSINE,
            )
        },
    )


def upsert_memory(entry: dict):
    """将记忆条目向量化写入（point id = memory id，便于同步启停/删除）。"""
    ensure_collection()
    dense, _ = embed.embed_query(entry["content"])
    _client().upsert(
        collection_name=COLLECTION,
        points=[models.PointStruct(
            id=entry["id"],
            vector={cfg.DENSE_NAME: dense},
            payload={
                "memory_id": entry["id"],
                "user_id": entry["user_id"],
                "content": entry["content"],
                "enabled": bool(entry.get("enabled", True)),
            },
        )],
    )


def update_enabled(memory_id: str, enabled: bool):
    """启停同步到向量 payload（检索过滤依赖 enabled）。"""
    client = _client()
    if not client.collection_exists(collection_name=COLLECTION):
        return
    client.set_payload(
        collection_name=COLLECTION,
        payload={"enabled": bool(enabled)},
        points=[memory_id],
    )


def search(user_id: str, query: str, top_k: int = 5) -> list:
    """按用户检索最相关记忆（filter user_id + enabled=true）。任何异常静默返回 []。"""
    try:
        client = _client()
        if not client.collection_exists(collection_name=COLLECTION):
            return []
        dense, _ = embed.embed_query(query)
        flt = models.Filter(must=[
            models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
            models.FieldCondition(key="enabled", match=models.MatchValue(value=True)),
        ])
        hits = client.query_points(
            collection_name=COLLECTION,
            query=dense, using=cfg.DENSE_NAME,
            query_filter=flt, limit=top_k, with_payload=True,
        ).points
        return [dict(p.payload or {}) for p in hits]
    except Exception:  # noqa: BLE001  # embedding 不可用 / Qdrant 故障：记忆不应阻断对话
        return []


def delete_points(memory_id: str):
    """遗忘时同步删除向量点。"""
    client = _client()
    if not client.collection_exists(collection_name=COLLECTION):
        return
    client.delete(
        collection_name=COLLECTION,
        points_selector=models.PointIdsList(points=[memory_id]),
    )
