"""入库异步任务：kb_ingest_tasks 表 + runner（SPEC-kb-ocr-ingest 能力 C2）。

进程边界（关键约束）：Qdrant local 嵌入式模式为单进程文件锁——
worker（子进程）只做 提取/切分/向量化 并返回 points；
`store.upsert_points` 与 reingest 的 `delete_document` 留在主进程、
且仅在 worker 成功后执行（失败零写入、旧片段保留）。
进度经 SQLite 跨进程可见；表与 agent.model_store.DB_PATH 同库。
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from agent import model_store
from kb import embed, ingest, store

KINDS = ("upload", "reingest")
STATUSES = ("queued", "running", "done", "failed")

# 测试注入："inline" 同进程直接执行（契约测试用，避免跨进程 flaky）
RUNNER = "process"

_executor = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_table(conn: sqlite3.Connection):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS kb_ingest_tasks (
            id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            total_pages INTEGER NOT NULL DEFAULT 0,
            done_pages INTEGER NOT NULL DEFAULT 0,
            chunks INTEGER,
            stats TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )


def _conn() -> sqlite3.Connection:
    """每次操作新开连接（跨进程写进度要求短事务）；DB_PATH 运行时读取以便测试隔离。"""
    conn = sqlite3.connect(model_store.DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    return conn


def _execute(sql: str, params: tuple = ()):
    conn = _conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _query(sql: str, params: tuple = ()) -> list:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _row_to_task(row: dict) -> dict:
    row["stats"] = json.loads(row["stats"]) if row.get("stats") else None
    return row


# ---------- 表操作 ----------

def create_task(kb_id: str, source: str, kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind 必须为 {KINDS} 之一，收到 {kind!r}")
    task_id = str(uuid.uuid4())
    now = _now()
    _execute(
        "INSERT INTO kb_ingest_tasks (id, kb_id, source, kind, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, 'queued', ?, ?)",
        (task_id, kb_id, source, kind, now, now),
    )
    return task_id


def set_status(task_id: str, status: str, *, chunks: int | None = None,
               stats: dict | None = None, error: str | None = None):
    if status not in STATUSES:
        raise ValueError(f"status 必须为 {STATUSES} 之一，收到 {status!r}")
    fields, vals = ["status = ?", "updated_at = ?"], [status, _now()]
    if chunks is not None:
        fields.append("chunks = ?")
        vals.append(chunks)
    if stats is not None:
        fields.append("stats = ?")
        vals.append(json.dumps(stats, ensure_ascii=False))
    if error is not None:
        fields.append("error = ?")
        vals.append(error)
    vals.append(task_id)
    _execute(f"UPDATE kb_ingest_tasks SET {', '.join(fields)} WHERE id = ?", tuple(vals))


def update_progress(task_id: str, done_pages: int, total_pages: int):
    _execute(
        "UPDATE kb_ingest_tasks SET done_pages = ?, total_pages = ?, updated_at = ? WHERE id = ?",
        (done_pages, total_pages, _now(), task_id),
    )


def get_task(task_id: str) -> dict | None:
    rows = _query("SELECT * FROM kb_ingest_tasks WHERE id = ?", (task_id,))
    return _row_to_task(rows[0]) if rows else None


def list_active(kb_id: str) -> list:
    rows = _query(
        "SELECT * FROM kb_ingest_tasks WHERE kb_id = ? AND status IN ('queued', 'running')"
        " ORDER BY created_at",
        (kb_id,),
    )
    return [_row_to_task(r) for r in rows]


def list_tasks(kb_id: str) -> list:
    rows = _query(
        "SELECT * FROM kb_ingest_tasks WHERE kb_id = ? ORDER BY created_at DESC",
        (kb_id,),
    )
    return [_row_to_task(r) for r in rows]


def cleanup_interrupted() -> int:
    """startup 清理：残留 queued/running → failed（不做断点续跑）。返回清理条数。"""
    return _execute(
        "UPDATE kb_ingest_tasks SET status = 'failed', error = '服务重启中断', updated_at = ?"
        " WHERE status IN ('queued', 'running')",
        (_now(),),
    )


# ---------- 执行 ----------

def _get_executor():
    global _executor
    if _executor is None:
        from concurrent.futures import ProcessPoolExecutor

        _executor = ProcessPoolExecutor(max_workers=1)  # 串行队列：上传是低频管理操作
    return _executor


def _worker(task_id: str, kb_id: str, path: str, source: str):
    """worker 侧（子进程或 inline）：置 running → 提取/切分/embed → 返回 (points, stats)。

    绝不触碰 store（进程边界约束）；进度逐页写 SQLite，主进程轮询可见。
    """
    set_status(task_id, "running")
    return ingest.prepare_points(
        kb_id, path, source=source,
        progress_cb=lambda done, total: update_progress(task_id, done, total),
    )


def _fail(task_id: str, exc: Exception):
    if isinstance(exc, (ingest.LowQualityExtraction, embed.EmbeddingUnavailable)):
        msg = str(exc)
    else:
        msg = f"入库失败: {exc}"
    set_status(task_id, "failed", error=msg)


def _finalize(task_id: str, points: list, stats: dict):
    """主进程侧：worker 成功后才写向量库；reingest 的删除也在此（失败不丢数据）。"""
    row = get_task(task_id)
    try:
        if row["kind"] == "reingest":
            store.delete_document(row["kb_id"], row["source"])
        n = store.upsert_points(row["kb_id"], points)
    except Exception as exc:  # noqa: BLE001
        _fail(task_id, exc)
        return
    set_status(task_id, "done", chunks=n, stats=stats)


def _on_future(task_id: str, future):
    try:
        points, stats = future.result()
    except Exception as exc:  # noqa: BLE001
        _fail(task_id, exc)
    else:
        _finalize(task_id, points, stats)


def start_ingest_task(kb_id: str, source: str, kind: str, path: str) -> str:
    """建任务并提交执行，立即返回 task_id（不阻塞请求）。path 为待入库文件实际路径。"""
    task_id = create_task(kb_id, source, kind)
    if RUNNER == "inline":
        try:
            points, stats = _worker(task_id, kb_id, path, source)
        except Exception as exc:  # noqa: BLE001
            _fail(task_id, exc)
        else:
            _finalize(task_id, points, stats)
    else:
        fut = _get_executor().submit(_worker, task_id, kb_id, path, source)
        fut.add_done_callback(lambda f: _on_future(task_id, f))
    return task_id
