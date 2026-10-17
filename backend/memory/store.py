"""记忆存储：SQLite memories 表（复用 agent.deep_agent.DB_PATH 同一文件）。"""

import uuid
from datetime import datetime, timezone

import aiosqlite

from agent.deep_agent import DB_PATH


async def init_memories_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'semantic',
                enabled INTEGER NOT NULL DEFAULT 1,
                source_thread TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        await conn.commit()


def _row_to_memory(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "content": row["content"],
        "memory_type": row["memory_type"],
        "enabled": bool(row["enabled"]),
        "source_thread": row["source_thread"],
        "created_at": row["created_at"],
    }


async def add_memory(
    user_id: str, content: str, source_thread: str | None = None,
    memory_type: str = "semantic",
) -> dict:
    """写入一条记忆并返回条目（Qdrant 向量由调用方另行走 vector.upsert_memory）。"""
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "content": content.strip(),
        "memory_type": memory_type,
        "enabled": True,
        "source_thread": source_thread,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO memories (id,user_id,content,memory_type,enabled,source_thread,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (entry["id"], entry["user_id"], entry["content"], entry["memory_type"],
             1, entry["source_thread"], entry["created_at"]),
        )
        await conn.commit()
    return entry


async def list_memories(user_id: str | None = None, enabled: bool | None = None) -> list:
    """管理列表，user_id / enabled 可选过滤，按创建时间倒序。"""
    sql = "SELECT * FROM memories"
    conds, params = [], []
    if user_id is not None:
        conds.append("user_id=?")
        params.append(user_id)
    if enabled is not None:
        conds.append("enabled=?")
        params.append(1 if enabled else 0)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY created_at DESC, rowid DESC"  # rowid 兜底同时间戳的稳定性
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
    return [_row_to_memory(r) for r in rows]


async def set_enabled(memory_id: str, enabled: bool) -> dict | None:
    """软停用/启用；注入与检索跳过 disabled。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE memories SET enabled=? WHERE id=?",
            (1 if enabled else 0, memory_id),
        )
        await conn.commit()
        if cur.rowcount == 0:
            return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c2 = await conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,))
        row = await c2.fetchone()
    return _row_to_memory(row) if row else None


async def forget_memory(memory_id: str) -> bool:
    """硬删除（Qdrant 点由调用方另行走 vector.delete_points）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        await conn.commit()
    return cur.rowcount > 0
