"""双向量 Embedding 封装：dense(OpenAI 兼容) + sparse(BM25, fastembed)。

密钥缺失或不可用时不崩溃，抛出可读错误交由上层转成提示。
"""

from qdrant_client import models

import kb.config as cfg
import kb.settings as settings


class EmbeddingUnavailable(RuntimeError):
    """dense 向量不可用（通常因未配置 embedding_api_key）。"""


_dense = None
_sparse = None


def reset_clients():
    """清空缓存的嵌入客户端，下次调用时按新配置重建。"""
    global _dense, _sparse
    _dense = None
    _sparse = None


def effective_dim() -> int:
    """嵌入向量生效维度：优先「模型配置」默认嵌入条目的 dim（单一事实来源），
    无条目或 dim<=0 时回退 KB 配置 embedding_dim。集合建 size 与调用共用本函数。"""
    dim = int(settings.get_settings()["embedding_dim"])
    try:
        from agent.model_store import get_default_sync

        emb = get_default_sync("embedding")
        if emb and int(emb.get("dim") or 0) > 0:
            return int(emb["dim"])
    except Exception:  # noqa: BLE001
        pass
    return dim


def _ensure_dense():
    global _dense
    if _dense is None:
        s = settings.get_settings()
        base_url = s["embedding_base_url"]
        model = s["embedding_model"]
        api_key = s["embedding_api_key"]
        # 统一模型配置：优先使用默认「嵌入模型」条目；无则回退 KB 配置/env
        try:
            from agent.model_store import get_default_sync

            emb = get_default_sync("embedding")
            if emb:
                if emb.get("base_url"):
                    base_url = emb["base_url"]
                if emb.get("model"):
                    model = emb["model"]
                if emb.get("api_key"):
                    api_key = emb["api_key"]
        except Exception:  # noqa: BLE001
            pass
        if not api_key:
            raise EmbeddingUnavailable(
                "未配置 embedding_api_key，dense 向量检索不可用。"
                "请在「模型配置」页添加嵌入模型，或在「知识库配置」页填入 OpenAI 兼容 Embedding 密钥。"
            )
        from langchain_openai import OpenAIEmbeddings

        # dimensions 与集合 schema 同源（effective_dim），如智谱 embedding-3 需显式指定
        _dense = OpenAIEmbeddings(
            model=model, api_key=api_key, base_url=base_url,
            dimensions=effective_dim(),
        )
    return _dense


def _ensure_sparse():
    global _sparse
    if _sparse is None:
        from fastembed import SparseTextEmbedding

        _sparse = SparseTextEmbedding(model_name=settings.get_settings()["sparse_model"])
    return _sparse


def _to_sparse_vec(sp) -> models.SparseVector:
    return models.SparseVector(
        indices=sp.indices.tolist(), values=sp.values.tolist()
    )


def embed_documents(texts: list) -> tuple:
    """返回 (dense_vectors, sparse_vectors)。

    注意：fastembed SparseTextEmbedding 只有 .embed() 方法（无 embed_documents）。
    """
    dense = _ensure_dense().embed_documents(texts)
    sparse = [_to_sparse_vec(s) for s in _ensure_sparse().embed(texts)]
    return dense, sparse


def embed_query(text: str) -> tuple:
    """返回 (dense_vector, sparse_vector)。"""
    dense = _ensure_dense().embed_query(text)
    sp = list(_ensure_sparse().embed([text]))[0]
    return dense, _to_sparse_vec(sp)


def sparse_query(text: str) -> models.SparseVector:
    """仅生成稀疏（BM25）向量——本地 fastembed，不依赖外部服务；检索降级路径用。"""
    sp = list(_ensure_sparse().embed([text]))[0]
    return _to_sparse_vec(sp)


def is_dense_available() -> bool:
    try:
        from agent.model_store import get_default_sync

        if get_default_sync("embedding"):
            return True
    except Exception:  # noqa: BLE001
        pass
    return bool(settings.get_settings()["embedding_api_key"])
