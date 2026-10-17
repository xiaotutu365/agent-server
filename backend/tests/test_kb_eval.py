"""L6 检索评测：recall@k/MRR 计算、evalset 读写与校验、run 双轨降级、API 契约。

不依赖真实 LLM：Ragas 路径全部 monkeypatch。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import models
import uuid

import kb.config as cfg
import kb.settings as kb_settings
from kb import eval as kb_eval
from kb import store
from kb.api import router


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    """评测集文件隔离到临时目录。"""
    monkeypatch.setattr(kb_eval, "_EVAL_DIR", str(tmp_path))
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_kb(kb_id, texts_by_source):
    store.drop_kb(kb_id)
    store.create_kb(kb_id)
    dim = kb_settings.get_settings()["embedding_dim"]
    pts = []
    for i, (source, text) in enumerate(texts_by_source.items()):
        pts.append(models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{kb_id}-{source}-{i}")),
            vector={cfg.DENSE_NAME: [0.1] * dim,
                    cfg.SPARSE_NAME: models.SparseVector(indices=[1, 2], values=[0.5, 0.5])},
            payload={"text": text, "source": source, "kb_id": kb_id, "chunk_idx": 0},
        ))
    store.upsert_points(kb_id, pts)


# ---------- recall@k / MRR 计算 ----------

def test_compute_recall_mrr_full_hit():
    hits = [{"source": "a.md"}, {"source": "b.md"}]
    recall, rr = kb_eval.compute_recall_mrr(hits, ["a.md", "b.md"])
    assert recall == 1.0
    assert rr == 1.0


def test_compute_recall_mrr_partial_and_rank():
    hits = [{"source": "x.md"}, {"source": "a.md"}]
    recall, rr = kb_eval.compute_recall_mrr(hits, ["a.md", "b.md"])
    assert recall == 0.5  # b.md 未召回
    assert rr == 0.5  # 首个命中文件排在第 2 位


def test_compute_recall_mrr_all_miss():
    recall, rr = kb_eval.compute_recall_mrr([{"source": "x.md"}], ["a.md"])
    assert recall == 0.0
    assert rr == 0.0


# ---------- evalset 读写与校验 ----------

def test_load_evalset_template_when_missing():
    data = kb_eval.load_evalset("no_such_kb")
    assert data["template"] is True
    assert len(data["items"]) >= 3
    assert all("query" in it and "expected_files" in it for it in data["items"])


def test_save_and_load_roundtrip():
    items = [{"query": "退货政策", "expected_files": ["policy.md"], "reference": "7 天无理由"}]
    saved = kb_eval.save_evalset("t_eval", items)
    assert saved[0]["reference"] == "7 天无理由"
    data = kb_eval.load_evalset("t_eval")
    assert data["template"] is False
    assert data["items"] == saved


def test_save_evalset_rejects_invalid():
    with pytest.raises(ValueError):
        kb_eval.save_evalset("t_eval", [])  # 空数组
    with pytest.raises(ValueError):
        kb_eval.save_evalset("t_eval", [{"expected_files": ["a.md"]}])  # 缺 query
    with pytest.raises(ValueError):
        kb_eval.save_evalset("t_eval", [{"query": "q", "expected_files": []}])  # 空 expected_files
    with pytest.raises(ValueError):
        kb_eval.save_evalset("t_eval", [{"query": "q", "expected_files": "a.md"}])  # 非数组


# ---------- run 双轨 ----------

def test_run_eval_self_metrics_and_degrade(monkeypatch):
    _seed_kb("t_eval_run", {"policy.md": "退货政策：7 天无理由。", "faq.md": "运费满 99 包邮。"})
    kb_eval.save_evalset("t_eval_run", [
        {"query": "退货政策是什么", "expected_files": ["policy.md"], "reference": "7 天无理由退货"},
        {"query": "运费怎么算", "expected_files": ["faq.md"]},
    ])
    monkeypatch.setattr(kb_eval, "_judge_llm", lambda: None)  # judge 不可用 → 降级

    import asyncio
    result = asyncio.run(kb_eval.run_eval("t_eval_run", top_k=3))

    assert result["summary"]["ragas_available"] is False
    assert "ragas_error" in result["summary"]
    assert 0.0 <= result["summary"]["recall_at_k"] <= 1.0
    assert 0.0 <= result["summary"]["mrr"] <= 1.0
    assert len(result["items"]) == 2
    for it in result["items"]:
        assert isinstance(it["hits"], list)
        for h in it["hits"]:
            assert set(h) >= {"text", "source", "chunk_idx", "score", "hit"}


def test_run_eval_ragas_path(monkeypatch):
    _seed_kb("t_eval_ragas", {"policy.md": "退货政策：7 天无理由。"})
    kb_eval.save_evalset("t_eval_ragas", [
        {"query": "退货政策", "expected_files": ["policy.md"]},  # 无 reference → 不进 ragas
        {"query": "几天可退", "expected_files": ["policy.md"], "reference": "7 天"},
    ])
    captured = {}

    def fake_scores(samples, llm):
        captured["n"] = len(samples)
        captured["refs"] = [s["reference"] for s in samples]
        return {"context_precision": 0.8, "context_recall": 1.0}

    monkeypatch.setattr(kb_eval, "_judge_llm", lambda: object())
    monkeypatch.setattr(kb_eval, "_ragas_scores", fake_scores)

    import asyncio
    result = asyncio.run(kb_eval.run_eval("t_eval_ragas", top_k=2))

    assert captured["n"] == 1, "只有带 reference 的条目进 Ragas"
    assert captured["refs"] == ["7 天"]
    assert result["summary"]["ragas_available"] is True
    assert result["summary"]["context_precision"] == 0.8
    assert result["summary"]["context_recall"] == 1.0


def test_run_eval_ragas_error_degrades(monkeypatch):
    _seed_kb("t_eval_err", {"policy.md": "退货政策：7 天无理由。"})
    kb_eval.save_evalset("t_eval_err", [
        {"query": "退货政策", "expected_files": ["policy.md"], "reference": "7 天"},
    ])
    monkeypatch.setattr(kb_eval, "_judge_llm", lambda: object())

    def boom(samples, llm):
        raise RuntimeError("LLM quota exceeded")

    monkeypatch.setattr(kb_eval, "_ragas_scores", boom)

    import asyncio
    result = asyncio.run(kb_eval.run_eval("t_eval_err", top_k=2))

    assert result["summary"]["ragas_available"] is False
    assert "quota" in result["summary"]["ragas_error"]
    assert len(result["items"]) == 1  # 自算结果不受影响


# ---------- API 契约 ----------

def test_api_evalset_endpoints(client):
    r0 = client.get("/api/kb/t_api_eval/evalset")
    assert r0.status_code == 200
    assert r0.json()["template"] is True

    r1 = client.put("/api/kb/t_api_eval/evalset", json={"items": [{"query": "q", "expected_files": []}]})
    assert r1.status_code == 400

    r2 = client.put("/api/kb/t_api_eval/evalset", json={
        "items": [{"query": "退货", "expected_files": ["policy.md"]}]
    })
    assert r2.status_code == 200
    assert r2.json()["items"][0]["query"] == "退货"

    r3 = client.get("/api/kb/t_api_eval/evalset")
    assert r3.json()["template"] is False
