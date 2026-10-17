"""L5 分片策略：_split 三策略行为 + settings 校验 + API 契约。

不依赖 embedding：只测切分逻辑与设置校验。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kb.settings as kb_settings
from kb import ingest
from kb.api import router


@pytest.fixture(autouse=True)
def _tmp_settings(tmp_path, monkeypatch):
    """设置持久化隔离到临时目录，避免污染 data/kb_settings.json。"""
    monkeypatch.setattr(kb_settings, "_SETTINGS_FILE", str(tmp_path / "s.json"))
    monkeypatch.setattr(kb_settings, "_settings", None)
    yield
    monkeypatch.setattr(kb_settings, "_settings", None)


# ---------- _split 三策略 ----------

def test_split_fixed_default():
    """默认策略 = 现行为：Recursive 固定长度+重叠切分。"""
    text = "这是一段用于测试的中文内容，包含足够多的字符。" * 60
    chunks = ingest._split(text)
    assert len(chunks) > 1
    assert all(len(c) <= kb_settings.get_settings()["chunk_size"] + 50 for c in chunks)


def test_split_markdown_by_headers():
    """markdown 策略：按标题层级切，不同标题节的内容不混在一个片段。"""
    kb_settings.save_settings({"chunk_strategy": "markdown"})
    text = (
        "# 标题A\n内容A第一段。\n## 子节A1\n内容A第二段。\n"
        "# 标题B\n内容B第一段。"
    )
    chunks = ingest._split(text)
    assert len(chunks) >= 2
    # 标题A 部分（含子节）与标题B 部分分离
    assert not any("内容A" in c and "内容B" in c for c in chunks)
    assert any("内容A第二段" in c for c in chunks)
    assert any("内容B第一段" in c for c in chunks)


def test_split_markdown_long_section_falls_back():
    """markdown 策略：单节超过 chunk_size 时按 Recursive 兜底再切。"""
    kb_settings.save_settings({"chunk_strategy": "markdown"})
    text = "# 长节\n" + ("超长内容句子。" * 300)
    chunks = ingest._split(text)
    assert len(chunks) >= 2


def test_split_blank_line_no_merge():
    """blank_line 策略：按空行分段，相邻段不合并（FAQ 分条）。"""
    kb_settings.save_settings({"chunk_strategy": "blank_line"})
    text = "问：退货政策是什么？\n\n答：7 天无理由。\n\n问：运费怎么算？\n\n答：满 99 免运费。"
    chunks = ingest._split(text)
    assert len(chunks) == 4
    # 不跨段合并：没有任何片段同时含两个问句
    assert not any("退货政策" in c and "运费" in c for c in chunks)


def test_split_blank_line_long_section_falls_back():
    """blank_line 策略：单段超 chunk_size 时兜底切，其余段保持原样。"""
    kb_settings.save_settings({"chunk_strategy": "blank_line"})
    text = ("长" * 1000) + "\n\n短段"
    chunks = ingest._split(text)
    assert len(chunks) >= 2
    assert chunks[-1] == "短段"


def test_split_unknown_strategy_falls_back_to_fixed():
    """settings 里出现未知策略值（如手工改 json）时按 fixed 处理，不抛异常。"""
    text = "测试内容。" * 30
    kb_settings._settings = dict(kb_settings.get_settings(), chunk_strategy="nope")
    assert ingest._split(text)  # 不抛异常且非空


# ---------- settings 校验与 API 契约 ----------

def test_save_settings_rejects_invalid_strategy():
    with pytest.raises(ValueError):
        kb_settings.save_settings({"chunk_strategy": "nope"})


def test_save_settings_accepts_valid_strategy():
    s = kb_settings.save_settings({"chunk_strategy": "markdown"})
    assert s["chunk_strategy"] == "markdown"
    # 持久化隔离校验：重新加载后仍生效
    kb_settings._settings = None
    assert kb_settings.get_settings()["chunk_strategy"] == "markdown"


def test_api_settings_roundtrip_and_400():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.get("/api/kb/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["chunk_strategy"] == "fixed"
    assert {x["value"] for x in data["chunk_strategies"]} == {"fixed", "markdown", "blank_line"}

    r2 = client.put("/api/kb/settings", json={"chunk_strategy": "nope"})
    assert r2.status_code == 400

    r3 = client.put("/api/kb/settings", json={"chunk_strategy": "blank_line"})
    assert r3.status_code == 200
    assert r3.json()["chunk_strategy"] == "blank_line"
