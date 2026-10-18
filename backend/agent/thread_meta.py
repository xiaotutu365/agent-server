"""会话级模型覆盖持久化（SPEC-session-model-select）。

表 thread_meta 每行一个会话的覆盖记录：
  - thread_id:  带用户前缀的 langgraph thread（u{user_id}:{thread_id}），主键
  - model_id:   覆盖的对话模型条目 id（model_configs.id）
  - updated_at: 最近更新时间

存于 agent_sessions.db（与 model_configs 同库）。按 lg_thread 存储天然按用户隔离。
"""

import os
from datetime import datetime, timezone

import aiosqlite

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agent_sessions.db"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_table(conn: aiosqlite.Connection):
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS thread_meta (
            thread_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )"""
    )


async def get_thread_model(thread_id: str) -> str | None:
    """返回会话覆盖的模型 id；无记录返回 None。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        cur = await conn.execute(
            "SELECT model_id FROM thread_meta WHERE thread_id=?", (thread_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def set_thread_model(thread_id: str, model_id: str):
    """写入/更新会话覆盖模型（覆盖写）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        await conn.execute(
            "INSERT INTO thread_meta (thread_id, model_id, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(thread_id) DO UPDATE SET model_id=excluded.model_id, "
            "updated_at=excluded.updated_at",
            (thread_id, model_id, _now()),
        )
        await conn.commit()


async def delete_thread_meta(thread_id: str):
    """删除会话覆盖记录（幂等；会话删除级联清理、回退默认时也走这里）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        await conn.execute("DELETE FROM thread_meta WHERE thread_id=?", (thread_id,))
        await conn.commit()


async def list_thread_models() -> dict:
    """全部会话覆盖（thread_id → model_id），供会话列表批量回显。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        cur = await conn.execute("SELECT thread_id, model_id FROM thread_meta")
        rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}
