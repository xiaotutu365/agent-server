"""kb.embed 稀疏向量封装：对齐 fastembed SparseTextEmbedding 真实 API。

回归背景：真实调用暴露 fastembed 模型只有 .embed() 方法（无 embed_documents/
embed_query），mock 掉 embed 层的既有测试无法发现。用桩钉住该契约。
"""

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest
from qdrant_client import models

import kb.embed as embed

# conftest 的 autouse fake_embed 会替换 embed.embed_query/embed_documents；
# 本模块在 import 时（fake 尚未生效）捕获真实实现，测试内恢复，专测封装层。
_real_embed_documents = embed.embed_documents
_real_embed_query = embed.embed_query


class _FakeSparseModel:
    """模拟 fastembed SparseTextEmbedding：只提供 .embed()，产出 numpy 数组。"""

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        for _ in texts:
            yield SimpleNamespace(
                indices=np.array([1, 2]), values=np.array([0.5, 0.5])
            )


class _FakeDense:
    def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2]


@pytest.fixture(autouse=True)
def _real_embed_fns(monkeypatch):
    monkeypatch.setattr(embed, "embed_documents", _real_embed_documents)
    monkeypatch.setattr(embed, "embed_query", _real_embed_query)


@pytest.fixture(autouse=True)
def _isolated_model_db(tmp_path, monkeypatch):
    """模型配置库指向临时文件，避免真实 agent_sessions.db 的默认嵌入条目泄漏进断言。"""
    from agent import model_store

    monkeypatch.setattr(model_store, "DB_PATH", str(tmp_path / "models.db"))


def _seed_default_embedding(dim):
    from agent import model_store

    return asyncio.run(model_store.create_model({
        "name": "emb-cfg", "type": "embedding", "base_url": "https://e",
        "model": "m", "api_key": "k", "dim": dim, "is_default": True,
    }))


def test_embed_documents_uses_fastembed_embed_api(monkeypatch):
    fake = _FakeSparseModel()
    monkeypatch.setattr(embed, "_sparse", fake)
    monkeypatch.setattr(embed, "_dense", _FakeDense())

    dense, sparse = embed.embed_documents(["a", "b"])
    assert len(dense) == 2
    assert all(isinstance(s, models.SparseVector) for s in sparse)
    assert fake.calls == [["a", "b"]], "应一次性批量调用 .embed()"


def test_embed_query_uses_fastembed_embed_api(monkeypatch):
    fake = _FakeSparseModel()
    monkeypatch.setattr(embed, "_sparse", fake)
    monkeypatch.setattr(embed, "_dense", _FakeDense())

    dense, sparse = embed.embed_query("hello")
    assert dense == [0.1, 0.2], "dense 应来自注入的 fake dense 模型"
    assert isinstance(sparse, models.SparseVector)
    assert fake.calls == [["hello"]]


def test_dense_client_passes_dimensions(monkeypatch):
    """embedding_dim 应作为 dimensions 参数传给 OpenAI 兼容 API（如智谱 embedding-3）。"""
    import kb.settings as kb_settings

    captured = {}

    class _SpyEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def embed_documents(self, texts):
            return [[0.0] * captured.get("dimensions", 4) for _ in texts]

        def embed_query(self, text):
            return [0.0] * captured.get("dimensions", 4)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _SpyEmbeddings)
    monkeypatch.setattr(embed, "_dense", None)
    monkeypatch.setattr(
        kb_settings, "_settings",
        dict(kb_settings.get_settings(), embedding_dim=1024, embedding_api_key="sk-test"),
    )

    embed.embed_documents(["x"])
    assert captured.get("dimensions") == 1024, "应传 dimensions=embedding_dim"


class _SpyEmbeddings:
    def __init__(self, **kwargs):
        _SpyEmbeddings.captured.update(kwargs)

    def embed_documents(self, texts):
        return [[0.0] * _SpyEmbeddings.captured.get("dimensions", 4) for _ in texts]

    def embed_query(self, text):
        return [0.0] * _SpyEmbeddings.captured.get("dimensions", 4)


def _spy_dense(monkeypatch):
    """把 OpenAIEmbeddings 换成记录构造参数的桩，并清空缓存实例。"""
    import langchain_openai

    _SpyEmbeddings.captured = {}
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _SpyEmbeddings)
    monkeypatch.setattr(embed, "_dense", None)


def test_dense_client_dimensions_from_model_store(monkeypatch):
    """回归 bugs/embed-dim-not-applied：默认嵌入条目 dim>0 时应覆盖 dimensions（单一事实来源）。"""
    import kb.settings as kb_settings

    _spy_dense(monkeypatch)
    monkeypatch.setattr(
        kb_settings, "_settings",
        dict(kb_settings.get_settings(), embedding_dim=256, embedding_api_key="sk-test"),
    )
    _seed_default_embedding(dim=1024)

    embed.embed_documents(["x"])
    assert _SpyEmbeddings.captured.get("dimensions") == 1024, "dimensions 应取模型配置 dim 而非 KB 配置"


def test_effective_dim_prefers_model_store_and_falls_back(monkeypatch):
    """effective_dim：有默认嵌入条目取其 dim；无条目回退 KB 配置 embedding_dim。"""
    import kb.settings as kb_settings

    monkeypatch.setattr(
        kb_settings, "_settings", dict(kb_settings.get_settings(), embedding_dim=256)
    )
    assert embed.effective_dim() == 256, "无模型条目应回退 KB 配置"
    _seed_default_embedding(dim=1024)
    assert embed.effective_dim() == 1024, "有默认条目应取模型配置 dim"


def test_create_kb_collection_uses_model_store_dim():
    """回归：新建知识库集合的向量 size 应与模型配置 dim 同源。"""
    import kb.config as cfg
    import kb.settings as kb_settings
    from kb import store

    kb_settings._settings = dict(kb_settings.get_settings(), embedding_dim=256)
    try:
        _seed_default_embedding(dim=1024)
        store.create_kb("kb-dim-check")
        info = store.get_client().get_collection(cfg.collection_name("kb-dim-check"))
        assert info.config.params.vectors[cfg.DENSE_NAME].size == 1024
    finally:
        kb_settings._settings = None
