import pytest

import kb.config as cfg
import kb.embed as embed


def test_no_key_unavailable(monkeypatch):
    monkeypatch.setattr(cfg, "EMBEDDING_API_KEY", "")
    embed._dense = None
    assert embed.is_dense_available() is False
    with pytest.raises(embed.EmbeddingUnavailable):
        embed._ensure_dense()
