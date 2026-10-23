"""kb/tasks.py 入库任务机制（SPEC-kb-ocr-ingest C2）：inline runner 契约测试。

表落在 model_store.DB_PATH（conftest isolated_model_store 已隔离到 tmp）。
"""

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from qdrant_client import models

import kb.config as cfg
from kb import ingest, ocr, store, tasks
from kb.api import router


@pytest.fixture(autouse=True)
def inline_runner(monkeypatch):
    """契约测试走同进程 runner，避免跨进程 flaky（spec C2 测试注入）。"""
    monkeypatch.setattr(tasks, "RUNNER", "inline")


def _blank_pdf(pages, path=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    if path is None:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _seed_point(kb_id, pid, text, source):
    store.upsert_points(kb_id, [models.PointStruct(
        id=pid,
        vector={cfg.DENSE_NAME: [0.1] * cfg.EMBEDDING_DIM,
                cfg.SPARSE_NAME: models.SparseVector(indices=[1], values=[0.5])},
        payload={"text": text, "source": source, "kb_id": kb_id, "chunk_idx": 0},
    )])


def _scroll_sources(kb_id):
    pts, _ = store.get_client().scroll(cfg.collection_name(kb_id), limit=100)
    return pts


def test_upload_task_done_and_searchable(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("知识库任务示例。" * 100, encoding="utf-8")
    task_id = tasks.start_ingest_task("t_upload", "a.txt", "upload", str(path))
    t = tasks.get_task(task_id)
    assert t["kind"] == "upload"
    assert t["status"] == "done", f"任务应完成：{t}"
    assert t["chunks"] > 0
    assert t["stats"] == {"pages": 0, "text_pages": 0, "ocr_pages": 0, "empty_pages": 0}
    pts = _scroll_sources("t_upload")
    assert len(pts) == t["chunks"]
    assert {p.payload["source"] for p in pts} == {"a.txt"}


def test_pdf_task_progress_and_stats(tmp_path, monkeypatch):
    # 图片页 OCR 桩返回足量中文块 → 3 页全部走 OCR 兜底
    monkeypatch.setattr(ocr, "_ocr_page",
                        lambda path, idx: [(10.0, 5.0, "CPU 由运算器和控制器组成。" * 20)])
    path = _blank_pdf(3)
    try:
        task_id = tasks.start_ingest_task("t_pdf", "c.pdf", "upload", path)
        t = tasks.get_task(task_id)
        assert t["status"] == "done", f"任务应完成：{t}"
        assert (t["done_pages"], t["total_pages"]) == (3, 3)
        assert t["stats"]["pages"] == 3
        assert t["stats"]["ocr_pages"] == 3
        assert t["chunks"] > 0
    finally:
        os.remove(path)


def test_low_quality_task_failed_zero_writes():
    """OCR 兜底后整份仍无字 → failed，向量库零写入（不建集合）。"""
    path = _blank_pdf(16)
    try:
        task_id = tasks.start_ingest_task("t_lowq", "scan.pdf", "upload", path)
        t = tasks.get_task(task_id)
        assert t["status"] == "failed"
        assert "OCR" in t["error"]
        assert not store.kb_exists("t_lowq"), "失败任务不得写入向量库"
    finally:
        os.remove(path)


def test_reingest_failure_keeps_old_chunks(tmp_path, monkeypatch):
    """重入库提取失败 → failed，旧片段保留（删除只在 worker 成功后执行）。"""
    monkeypatch.setattr(ingest, "UPLOADS_ROOT", str(tmp_path))
    kb_id, src = "t_reingest_bad", "bad.pdf"
    store.create_kb(kb_id)
    _seed_point(kb_id, "00000000-0000-0000-0000-000000000001", "旧片段", src)
    archive = tmp_path / kb_id
    archive.mkdir()
    _blank_pdf(16, path=str(archive / src))
    task_id = tasks.start_ingest_task(kb_id, src, "reingest", str(archive / src))
    t = tasks.get_task(task_id)
    assert t["status"] == "failed"
    pts = _scroll_sources(kb_id)
    assert len(pts) == 1 and pts[0].payload["text"] == "旧片段"


def test_reingest_success_replaces_old_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "UPLOADS_ROOT", str(tmp_path))
    kb_id, src = "t_reingest_ok", "doc.txt"
    store.create_kb(kb_id)
    _seed_point(kb_id, "00000000-0000-0000-0000-000000000002", "旧片段", src)
    new_file = tmp_path / "new.txt"
    new_file.write_text("全新内容示例。" * 100, encoding="utf-8")
    task_id = tasks.start_ingest_task(kb_id, src, "reingest", str(new_file))
    t = tasks.get_task(task_id)
    assert t["status"] == "done", f"任务应完成：{t}"
    pts = _scroll_sources(kb_id)
    assert len(pts) == t["chunks"]
    assert all("旧片段" not in p.payload["text"] for p in pts)
    assert {p.payload["source"] for p in pts} == {src}


def test_cleanup_interrupted_marks_failed():
    t1 = tasks.create_task("kb_clean", "f1.txt", "upload")
    t2 = tasks.create_task("kb_clean", "f2.txt", "upload")
    tasks.set_status(t2, "running")
    t3 = tasks.create_task("kb_clean", "f3.txt", "upload")
    tasks.set_status(t3, "done", chunks=1)
    n = tasks.cleanup_interrupted()
    assert n == 2
    for tid in (t1, t2):
        t = tasks.get_task(tid)
        assert t["status"] == "failed"
        assert t["error"] == "服务重启中断"
    assert tasks.get_task(t3)["status"] == "done"


def test_list_active_filters_status_and_kb():
    ta = tasks.create_task("kbA", "a.txt", "upload")
    tb = tasks.create_task("kbB", "b.txt", "upload")
    tc = tasks.create_task("kbA", "c.txt", "upload")
    tasks.set_status(tc, "done", chunks=1)
    ids = [t["id"] for t in tasks.list_active("kbA")]
    assert ids == [ta]
    assert [t["id"] for t in tasks.list_active("kbB")] == [tb]


def test_worker_does_not_touch_store(tmp_path, monkeypatch):
    """进程边界：worker 只做提取/切分/向量化，不得调用 store 写入接口。"""
    def _boom(*a, **k):
        raise AssertionError("worker 不得触碰 store")

    monkeypatch.setattr(store, "upsert_points", _boom)
    monkeypatch.setattr(store, "delete_document", _boom)
    path = tmp_path / "w.txt"
    path.write_text("边界内容示例。" * 100, encoding="utf-8")
    task_id = tasks.create_task("t_worker", "w.txt", "upload")
    points, stats = tasks._worker(task_id, "t_worker", str(path), "w.txt")
    assert points, "worker 应产出 points"
    assert stats["pages"] == 0
    assert tasks.get_task(task_id)["status"] == "running"


def test_table_creation_is_idempotent():
    conn = tasks._conn()
    tasks._ensure_table(conn)
    tasks._ensure_table(conn)
    conn.close()
    tid = tasks.create_task("kb_idem", "x.txt", "upload")
    t = tasks.get_task(tid)
    assert t["status"] == "queued"
    assert t["total_pages"] == 0 and t["done_pages"] == 0


# ---------- API 202 契约（SPEC-kb-ocr-ingest C2 契约表） ----------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "UPLOADS_ROOT", str(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _task(client, task_id):
    r = client.get(f"/api/kb/ingest-tasks/{task_id}")
    assert r.status_code == 200
    return r.json()


def test_api_upload_202_and_poll_done(client):
    r = client.post(
        "/api/kb/t_api/documents",
        files={"file": ("a.txt", "知识库接口示例。" * 100, "text/plain")},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["kb_id"] == "t_api" and body["file"] == "a.txt"
    t = _task(client, body["task_id"])
    assert t["status"] == "done"
    assert t["chunks"] > 0
    pts, _ = store.get_client().scroll(cfg.collection_name("t_api"), limit=10)
    assert len(pts) == t["chunks"]


def test_api_get_task_404(client):
    assert client.get("/api/kb/ingest-tasks/no-such-task").status_code == 404


def test_api_upload_invalid_kb_400(client):
    r = client.post(
        "/api/kb/bad%20id/documents", files={"file": ("a.txt", "x", "text/plain")}
    )
    assert r.status_code == 400


def test_api_list_active_tasks(client):
    t1 = tasks.create_task("t_list", "a.txt", "upload")
    t2 = tasks.create_task("t_list", "b.txt", "upload")
    tasks.set_status(t2, "done", chunks=1)
    r = client.get("/api/kb/t_list/ingest-tasks", params={"active": "true"})
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["tasks"]]
    assert ids == [t1]


def test_api_reingest_failure_keeps_old_chunks(client):
    """留档为整份无字 PDF → 重入库 202→failed，旧片段保留。"""
    kb_id, src = "t_api_bad", "scan.pdf"
    store.create_kb(kb_id)
    _seed_point(kb_id, "00000000-0000-0000-0000-00000000000a", "旧片段", src)
    archive = os.path.join(ingest.UPLOADS_ROOT, kb_id)
    os.makedirs(archive, exist_ok=True)
    _blank_pdf(16, path=os.path.join(archive, src))
    r = client.post(f"/api/kb/{kb_id}/documents/reingest", params={"file": src})
    assert r.status_code == 202
    t = _task(client, r.json()["task_id"])
    assert t["status"] == "failed"
    assert "OCR" in t["error"]
    pts, _ = store.get_client().scroll(cfg.collection_name(kb_id), limit=100)
    assert len(pts) == 1 and pts[0].payload["text"] == "旧片段"
