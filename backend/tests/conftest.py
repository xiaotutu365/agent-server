"""测试夹具：内存版 Qdrant + mock embedding，无需外部服务/网络。"""

import pytest
from qdrant_client import QdrantClient, models

import kb.config as cfg
import kb.embed as embed
from kb import store


@pytest.fixture(autouse=True)
def memory_qdrant():
    store._client = QdrantClient(":memory:")
    yield
    store._client = None


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """设置隔离：屏蔽真实 data/kb_settings.json，测试一律用默认值。

    回归背景：外部脚本/真实配置（如 embedding_dim=1024）会泄漏进测试，
    与按 cfg.EMBEDDING_DIM 种子的向量维度冲突。
    """
    import kb.settings as kb_settings

    monkeypatch.setattr(kb_settings, "_SETTINGS_FILE", str(tmp_path / "kb_settings.json"))
    monkeypatch.setattr(kb_settings, "_settings", None)
    yield


@pytest.fixture(autouse=True)
def isolated_model_store(tmp_path, monkeypatch):
    """屏蔽真实「模型配置」库：测试不依赖 data/ 下 model_configs 状态。

    回归背景（bugs/kb-tests-model-store-leak.md）：用户配置 dim=1024 嵌入模型后，
    embed.effective_dim() 读到真实条目，与 fake_embed 的 cfg.EMBEDDING_DIM(1536)
    冲突，kb 测试建集合维度不一致。
    注意：只隔离 DB_PATH 而非 get_default_sync 本身——
    test_kb_embed_sparse 等测试要在自建 DB 上验证 model_store 读取路径。
    """
    from agent import model_store

    monkeypatch.setattr(model_store, "DB_PATH", str(tmp_path / "isolated_models.db"))


@pytest.fixture(autouse=True)
def stub_ocr(monkeypatch):
    """单测不跑真 OCR：图片页一律返回空块（扫描件 → OCR 兜底后仍无字 → 被闸门拒绝）。

    回归背景：kb/ocr.py 的渲染/识别接缝依赖 pymupdf/rapidocr，单测不得依赖真实引擎。
    慢集成测试（@pytest.mark.ocr）用 monkeypatch.setattr(ocr, "_ocr_page", ocr.ocr_page) 还原真实现。
    """
    from kb import ocr

    monkeypatch.setattr(ocr, "_ocr_page", lambda path, idx: [])


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    def fake_query(text):
        return [0.1] * cfg.EMBEDDING_DIM, models.SparseVector(
            indices=[1, 2], values=[0.5, 0.5]
        )

    def fake_docs(texts):
        dense = [[0.1] * cfg.EMBEDDING_DIM for _ in texts]
        sparse = [models.SparseVector(indices=[1], values=[0.5]) for _ in texts]
        return dense, sparse

    monkeypatch.setattr(embed, "embed_query", fake_query)
    monkeypatch.setattr(embed, "embed_documents", fake_docs)
