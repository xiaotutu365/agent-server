"""流程存储：SQLite flows / flow_runs 两表（复用 agent.deep_agent.DB_PATH 同一文件）。

SPEC-flow-config 3.1：flows 存流程定义（JSON DSL，version 自增）；
flow_runs 存实例状态（running/waiting_human/done/failed/cancelled），
outputs 冗余落库避免列表页反序列化 checkpointer 大 state。
"""

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from agent.deep_agent import DB_PATH


async def init_flow_tables():
    """幂等建表（与 memory.store.init_memories_table 同模式）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS flows (
                flow_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                definition TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS flow_runs (
                run_id TEXT PRIMARY KEY,
                flow_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                current_node TEXT,
                input TEXT NOT NULL,
                outputs TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        await conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_flow(row) -> dict:
    return {
        "flow_id": row["flow_id"],
        "name": row["name"],
        "version": row["version"],
        "definition": json.loads(row["definition"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_run(row) -> dict:
    return {
        "run_id": row["run_id"],
        "flow_id": row["flow_id"],
        "status": row["status"],
        "current_node": row["current_node"],
        "input": json.loads(row["input"]),
        "outputs": json.loads(row["outputs"]) if row["outputs"] else {},
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create_flow(name: str, definition: dict) -> dict:
    now = _now()
    flow = {
        "flow_id": str(uuid.uuid4()),
        "name": name,
        "version": 1,
        "definition": definition,
        "created_at": now,
        "updated_at": now,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO flows (flow_id,name,version,definition,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (flow["flow_id"], name, 1, json.dumps(definition, ensure_ascii=False), now, now),
        )
        await conn.commit()
    return flow


async def get_flow(flow_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM flows WHERE flow_id=?", (flow_id,))
        row = await cur.fetchone()
    return _row_to_flow(row) if row else None


async def list_flows() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM flows ORDER BY updated_at DESC, rowid DESC")
        rows = await cur.fetchall()
    return [_row_to_flow(r) for r in rows]


async def update_flow(flow_id: str, name: str | None = None,
                      definition: dict | None = None) -> dict | None:
    """部分更新；任意更新都 bump version（SPEC 3.4）。不存在返回 None。"""
    current = await get_flow(flow_id)
    if not current:
        return None
    new_name = name if name is not None else current["name"]
    new_def = definition if definition is not None else current["definition"]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE flows SET name=?, definition=?, version=version+1, updated_at=? "
            "WHERE flow_id=?",
            (new_name, json.dumps(new_def, ensure_ascii=False), _now(), flow_id),
        )
        await conn.commit()
    return await get_flow(flow_id)


async def delete_flow(flow_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("DELETE FROM flows WHERE flow_id=?", (flow_id,))
        await conn.commit()
    return cur.rowcount > 0


async def create_run(flow_id: str, run_input: dict) -> dict:
    now = _now()
    run = {
        "run_id": str(uuid.uuid4()),
        "flow_id": flow_id,
        "status": "running",
        "current_node": None,
        "input": run_input,
        "outputs": {},
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO flow_runs (run_id,flow_id,status,current_node,input,outputs,error,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (run["run_id"], flow_id, "running", None,
             json.dumps(run_input, ensure_ascii=False), "{}", None, now, now),
        )
        await conn.commit()
    return run


async def get_run(run_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM flow_runs WHERE run_id=?", (run_id,))
        row = await cur.fetchone()
    return _row_to_run(row) if row else None


async def list_runs(flow_id: str | None = None) -> list:
    sql = "SELECT * FROM flow_runs"
    params: list = []
    if flow_id is not None:
        sql += " WHERE flow_id=?"
        params.append(flow_id)
    sql += " ORDER BY created_at DESC, rowid DESC"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
    return [_row_to_run(r) for r in rows]


async def update_run(run_id: str, status: str | None = None, current_node: str | None = None,
                     outputs: dict | None = None, error: str | None = None) -> dict | None:
    """部分更新实例状态；outputs 为整体替换（调用方传入累积后的全量字典）。"""
    sets, params = ["updated_at=?"], [_now()]
    if status is not None:
        sets.append("status=?")
        params.append(status)
    if current_node is not None:
        sets.append("current_node=?")
        params.append(current_node)
    if outputs is not None:
        sets.append("outputs=?")
        params.append(json.dumps(outputs, ensure_ascii=False))
    if error is not None:
        sets.append("error=?")
        params.append(error)
    params.append(run_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(f"UPDATE flow_runs SET {', '.join(sets)} WHERE run_id=?", params)
        await conn.commit()
    return await get_run(run_id)
