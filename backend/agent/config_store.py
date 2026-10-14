"""Agent 配置持久化（多 Agent，存于 SQLite data/agent_sessions.db）。

表 agent_config 每行一个 Agent，含 is_default 标记（全局唯一默认，聊天固定使用）。
后台可做 Agent 的列表 / 新增 / 编辑 / 删除 / 设为默认，保存后影响默认 Agent 时热重建。
"""

import json
import os
import uuid
from datetime import datetime, timezone

import aiosqlite

from agent.deep_agent import DB_PATH, SYSTEM_PROMPT, INTERRUPT_TOOLS
from agent.tool_registry import ALL_TOOL_NAMES

DEFAULT_CONFIG = {
    "name": "默认 DeepAgent",
    "system_prompt": SYSTEM_PROMPT,
    "model_name": os.getenv("MODEL_NAME", "deepseek-flash"),
    "temperature": 0.3,
    "tools_enabled": list(ALL_TOOL_NAMES),
    "hitl": dict(INTERRUPT_TOOLS),
    "memory_enabled": True,
    "kb_enabled": True,
    "mcp_servers": [],  # 外部 MCP 服务器列表（见 agent/mcp_tools.py）
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_table(conn: aiosqlite.Connection):
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS agent_config (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            model_name TEXT NOT NULL,
            temperature REAL NOT NULL,
            tools_enabled TEXT NOT NULL,
            hitl TEXT NOT NULL,
            memory_enabled INTEGER NOT NULL,
            kb_enabled INTEGER NOT NULL,
            mcp_servers TEXT NOT NULL DEFAULT '[]',
            is_default INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    # 迁移旧表：若缺少 is_default 列则补上，并把历史 default 行设为默认 Agent
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("PRAGMA table_info(agent_config)")
    cols = {r["name"] for r in await cur.fetchall()}
    if "is_default" not in cols:
        await conn.execute(
            "ALTER TABLE agent_config ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
        )
        await conn.execute(
            "UPDATE agent_config SET is_default=1 WHERE id='default' "
            "AND NOT EXISTS (SELECT 1 FROM agent_config WHERE is_default=1)"
        )
        await conn.commit()
    # 迁移：缺 mcp_servers 列则补上
    if "mcp_servers" not in cols:
        await conn.execute(
            "ALTER TABLE agent_config ADD COLUMN mcp_servers TEXT NOT NULL DEFAULT '[]'"
        )
        await conn.commit()


def _row_to_config(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "system_prompt": row["system_prompt"],
        "model_name": row["model_name"],
        "temperature": row["temperature"],
        "tools_enabled": json.loads(row["tools_enabled"]),
        "hitl": json.loads(row["hitl"]),
        "memory_enabled": bool(row["memory_enabled"]),
        "kb_enabled": bool(row["kb_enabled"]),
        "mcp_servers": json.loads(row["mcp_servers"]),
        "is_default": bool(row["is_default"]),
        "updated_at": row["updated_at"],
    }


def _filter_tools(tools, hitl):
    return (
        [t for t in (tools or []) if t in ALL_TOOL_NAMES],
        {t: ds for t, ds in (hitl or {}).items() if t in ALL_TOOL_NAMES},
    )


async def load_default_config() -> dict:
    """返回默认 Agent 配置；库空则写入默认；无默认标记则取第一行。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM agent_config ORDER BY is_default DESC, updated_at DESC"
        )
        rows = await cur.fetchall()
        if not rows:
            cfg = dict(DEFAULT_CONFIG, id=str(uuid.uuid4()), is_default=True, updated_at=_now())
            await conn.execute(
                "INSERT INTO agent_config "
                "(id,name,system_prompt,model_name,temperature,tools_enabled,hitl,"
                "memory_enabled,kb_enabled,is_default,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cfg["id"], cfg["name"], cfg["system_prompt"], cfg["model_name"],
                    cfg["temperature"], json.dumps(cfg["tools_enabled"], ensure_ascii=False),
                    json.dumps(cfg["hitl"], ensure_ascii=False),
                    int(cfg["memory_enabled"]), int(cfg["kb_enabled"]), 1, cfg["updated_at"],
                ),
            )
            await conn.commit()
            return cfg
        default = next((r for r in rows if r["is_default"]), rows[0])
        return _row_to_config(default)


async def list_agents() -> list:
    """所有 Agent 摘要（含是否为默认）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM agent_config ORDER BY is_default DESC, updated_at DESC"
        )
        rows = await cur.fetchall()
    return [_row_to_config(r) for r in rows]


async def get_agent(agent_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM agent_config WHERE id=?", (agent_id,))
        row = await cur.fetchone()
    return _row_to_config(row) if row else None


async def create_agent(data: dict) -> dict:
    """新增 Agent；库为空时自动设为默认。返回创建后的完整配置。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT COUNT(*) AS c FROM agent_config")
        count = (await cur.fetchone())["c"]
        is_default = 1 if count == 0 else 0
        tools, hitl = _filter_tools(data.get("tools_enabled"), data.get("hitl"))
        cfg = {
            "id": str(uuid.uuid4()),
            "name": data.get("name", "未命名 Agent"),
            "system_prompt": data.get("system_prompt", DEFAULT_CONFIG["system_prompt"]),
            "model_name": data.get("model_name", DEFAULT_CONFIG["model_name"]),
            "temperature": float(data.get("temperature", 0.3)),
            "tools_enabled": tools,
            "hitl": hitl,
            "memory_enabled": bool(data.get("memory_enabled", True)),
            "kb_enabled": bool(data.get("kb_enabled", True)),
            "mcp_servers": data.get("mcp_servers", []),
            "is_default": is_default,
            "updated_at": _now(),
        }
        await conn.execute(
            "INSERT INTO agent_config "
            "(id,name,system_prompt,model_name,temperature,tools_enabled,hitl,"
            "memory_enabled,kb_enabled,mcp_servers,is_default,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cfg["id"], cfg["name"], cfg["system_prompt"], cfg["model_name"],
                cfg["temperature"], json.dumps(cfg["tools_enabled"], ensure_ascii=False),
                json.dumps(cfg["hitl"], ensure_ascii=False),
                int(cfg["memory_enabled"]), int(cfg["kb_enabled"]),
                json.dumps(cfg["mcp_servers"], ensure_ascii=False),
                is_default, cfg["updated_at"],
            ),
        )
        await conn.commit()
    return cfg


async def update_agent(agent_id: str, data: dict) -> dict | None:
    """更新 Agent（按 id）。is_default 置真时清除其他默认保证唯一。
    缺失字段沿用原值（便于「设为默认」等局部更新）。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM agent_config WHERE id=?", (agent_id,))
        row = await cur.fetchone()
        if not row:
            return None
        is_default = 1 if data.get("is_default", bool(row["is_default"])) else 0
        if is_default:
            await conn.execute("UPDATE agent_config SET is_default=0 WHERE id!=?", (agent_id,))
        tools, hitl = _filter_tools(
            data.get("tools_enabled", json.loads(row["tools_enabled"])),
            data.get("hitl", json.loads(row["hitl"])),
        )
        cfg = {
            "id": agent_id,
            "name": data.get("name", row["name"]),
            "system_prompt": data.get("system_prompt", row["system_prompt"]),
            "model_name": data.get("model_name", row["model_name"]),
            "temperature": float(data.get("temperature", row["temperature"])),
            "tools_enabled": tools,
            "hitl": hitl,
            "memory_enabled": bool(data.get("memory_enabled", bool(row["memory_enabled"]))),
            "kb_enabled": bool(data.get("kb_enabled", bool(row["kb_enabled"]))),
            "mcp_servers": data.get("mcp_servers", json.loads(row["mcp_servers"])),
            "is_default": is_default,
            "updated_at": _now(),
        }
        await conn.execute(
            """UPDATE agent_config SET
                 name=?, system_prompt=?, model_name=?, temperature=?,
                 tools_enabled=?, hitl=?, memory_enabled=?, kb_enabled=?,
                 mcp_servers=?, is_default=?, updated_at=?
               WHERE id=?""",
            (
                cfg["name"], cfg["system_prompt"], cfg["model_name"], cfg["temperature"],
                json.dumps(cfg["tools_enabled"], ensure_ascii=False),
                json.dumps(cfg["hitl"], ensure_ascii=False),
                int(cfg["memory_enabled"]), int(cfg["kb_enabled"]),
                json.dumps(cfg["mcp_servers"], ensure_ascii=False),
                is_default, cfg["updated_at"], agent_id,
            ),
        )
        await conn.commit()
    return cfg


async def delete_agent(agent_id: str) -> dict:
    """删除 Agent；禁止删除最后一个。若删的是默认且还有其它，把第一个设为默认。
    返回 {deleted, new_default, rebuild}。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM agent_config ORDER BY is_default DESC, updated_at DESC"
        )
        rows = await cur.fetchall()
        if len(rows) <= 1:
            raise ValueError("至少保留一个 Agent，无法删除")
        target = next((r for r in rows if r["id"] == agent_id), None)
        if not target:
            raise ValueError("Agent 不存在")
        await conn.execute("DELETE FROM agent_config WHERE id=?", (agent_id,))
        new_default = None
        rebuild = False
        if target["is_default"]:
            nxt = next((r for r in rows if r["id"] != agent_id), None)
            if nxt:
                await conn.execute("UPDATE agent_config SET is_default=1 WHERE id=?", (nxt["id"],))
                new_default = nxt["id"]
                rebuild = True
        await conn.commit()
    return {"deleted": agent_id, "new_default": new_default, "rebuild": rebuild}
