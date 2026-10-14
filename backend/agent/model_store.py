"""统一模型配置持久化（大模型 / 嵌入 / 重排等，存于 SQLite agent_sessions.db）。

表 model_configs 每行一个模型条目：
  - type:    llm | embedding | rerank
  - name:    展示名（如 default-llm）
  - base_url / api_key / model: 调用所需
  - dim:     向量维度（嵌入模型参考用）
  - is_default: 每类型唯一默认
  - extra:   类型相关扩展参数（JSON）

调用方（build_agent / kb.embed / kb.retrieval）通过 get_default(type) 读取当前生效模型，
无配置时回退到原有环境变量/KB 配置，保证兼容。
"""

import asyncio
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone

import aiosqlite

# 与 deep_agent.DB_PATH 同一文件，避免循环导入（此处自行计算路径）
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agent_sessions.db"
)

MODEL_TYPES = ("llm", "embedding", "rerank")
TYPE_LABELS = {"llm": "大模型", "embedding": "嵌入模型", "rerank": "重排模型"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_table(conn: aiosqlite.Connection):
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS model_configs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            base_url TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            dim INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            extra TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )"""
    )


def _row_to_model(row) -> dict:
    extra = {}
    try:
        extra = json.loads(row["extra"] or "{}")
    except Exception:  # noqa: BLE001
        pass
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "model": row["model"],
        "dim": row["dim"],
        "is_default": bool(row["is_default"]),
        "extra": extra,
        "updated_at": row["updated_at"],
    }


async def list_models(type: str | None = None) -> list:
    """列出模型；可按类型过滤。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        if type:
            cur = await conn.execute(
                "SELECT * FROM model_configs WHERE type=? ORDER BY is_default DESC, updated_at DESC",
                (type,),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM model_configs ORDER BY type, is_default DESC, updated_at DESC"
            )
        rows = await cur.fetchall()
    return [_row_to_model(r) for r in rows]


async def get_model(model_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM model_configs WHERE id=?", (model_id,))
        row = await cur.fetchone()
    return _row_to_model(row) if row else None


async def get_default(type: str) -> dict | None:
    """返回某类型的默认模型（无则 None）。供实际调用处读取。"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM model_configs WHERE type=? AND is_default=1 "
            "ORDER BY updated_at DESC LIMIT 1",
            (type,),
        )
        row = await cur.fetchone()
    return _row_to_model(row) if row else None


def get_default_sync(type: str) -> dict | None:
    """同步版 get_default：供 embed 等同步上下文使用（std 库 sqlite3）。"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM model_configs WHERE type=? AND is_default=1 "
            "ORDER BY updated_at DESC LIMIT 1",
            (type,),
        )
        row = cur.fetchone()
        conn.close()
    except Exception:  # noqa: BLE001
        return None
    return _row_to_model(row) if row else None


def _validate_model_data(data: dict):
    """必填校验：名称 / 接口地址 / 模型名 为通用必填；嵌入模型还需维度(>0)。"""
    mtype = data.get("type")
    name = (data.get("name") or "").strip()
    model = (data.get("model") or "").strip()
    base_url = (data.get("base_url") or "").strip()
    if not name:
        raise ValueError("请填写模型名称(name)")
    if not model:
        raise ValueError("请填写模型(model)")
    if not base_url:
        raise ValueError("请填写接口地址(base_url)")
    if mtype == "embedding":
        try:
            dim = int(data.get("dim", 0) or 0)
        except (TypeError, ValueError):
            dim = 0
        if dim <= 0:
            raise ValueError("嵌入模型请填写维度(dim)，且需大于 0")


async def create_model(data: dict) -> dict:
    mtype = data.get("type")
    if mtype not in MODEL_TYPES:
        raise ValueError("未知的模型类型")
    _validate_model_data(data)
    is_default = bool(data.get("is_default", False))
    cfg = {
        "id": str(uuid.uuid4()),
        "name": data.get("name", "") or TYPE_LABELS.get(mtype, mtype),
        "type": mtype,
        "base_url": data.get("base_url", "") or "",
        "api_key": data.get("api_key", "") or "",
        "model": data.get("model", "") or "",
        "dim": int(data.get("dim", 0) or 0),
        "is_default": 1 if is_default else 0,
        "extra": data.get("extra", {}) or {},
        "updated_at": _now(),
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        if is_default:
            await conn.execute(
                "UPDATE model_configs SET is_default=0 WHERE type=?", (mtype,)
            )
        await conn.execute(
            "INSERT INTO model_configs "
            "(id,name,type,base_url,api_key,model,dim,is_default,extra,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                cfg["id"], cfg["name"], cfg["type"], cfg["base_url"], cfg["api_key"],
                cfg["model"], cfg["dim"], cfg["is_default"],
                json.dumps(cfg["extra"], ensure_ascii=False), cfg["updated_at"],
            ),
        )
        await conn.commit()
    return cfg


async def update_model(model_id: str, data: dict) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM model_configs WHERE id=?", (model_id,))
        row = await cur.fetchone()
        if not row:
            return None
        mtype = data.get("type", row["type"])
        if mtype not in MODEL_TYPES:
            raise ValueError("未知的模型类型")
        is_default = 1 if data.get("is_default", bool(row["is_default"])) else 0
        if is_default:
            await conn.execute(
                "UPDATE model_configs SET is_default=0 WHERE type=? AND id!=?",
                (mtype, model_id),
            )
        extra = data.get("extra", json.loads(row["extra"] or "{}"))
        cfg = {
            "id": model_id,
            "name": data.get("name", row["name"]),
            "type": mtype,
            "base_url": data.get("base_url", row["base_url"]),
            "api_key": data.get("api_key", row["api_key"]),
            "model": data.get("model", row["model"]),
            "dim": int(data.get("dim", row["dim"]) or 0),
            "is_default": is_default,
            "extra": extra,
            "updated_at": _now(),
        }
        _validate_model_data(cfg)
        await conn.execute(
            """UPDATE model_configs SET
                 name=?, type=?, base_url=?, api_key=?, model=?, dim=?,
                 is_default=?, extra=?, updated_at=? WHERE id=?""",
            (
                cfg["name"], cfg["type"], cfg["base_url"], cfg["api_key"], cfg["model"],
                cfg["dim"], cfg["is_default"],
                json.dumps(cfg["extra"], ensure_ascii=False), cfg["updated_at"], model_id,
            ),
        )
        await conn.commit()
    return cfg


async def delete_model(model_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        await _ensure_table(conn)
        await conn.execute("DELETE FROM model_configs WHERE id=?", (model_id,))
        await conn.commit()
    return {"deleted": model_id}


async def test_model_connection(cfg: dict) -> dict:
    """按配置发起一次最小化真实请求，验证连通性。返回 {ok, detail, latency_ms}。

    按 type 选择不同探测方式：
      - llm:       一次极短对话（init_chat_model）
      - embedding: 一次向量化（OpenAIEmbeddings）
      - rerank:    一次重排（POST base_url，兼容 Cohere/Jina/Voyage 等）
    """
    t0 = time.monotonic()
    mtype = cfg.get("type") or "llm"
    base_url = (cfg.get("base_url") or "").strip()
    api_key = (cfg.get("api_key") or "").strip()
    model = (cfg.get("model") or "").strip()
    dim = cfg.get("dim") or 0
    if not model:
        return {"ok": False, "detail": "请先填写模型名(model)", "latency_ms": 0}
    try:
        if mtype == "llm":
            from langchain.chat_models import init_chat_model

            llm = init_chat_model(
                model, model_provider="openai", api_key=api_key or None,
                base_url=base_url or None, temperature=0.1, max_tokens=16,
                timeout=15, max_retries=1, streaming=False,
            )
            out = await asyncio.to_thread(llm.invoke, "ping")
            text = getattr(out, "content", "") or ""
            if not text:
                raise RuntimeError("模型返回内容为空")
            detail = f"对话成功，返回 {len(str(text))} 字符"
        elif mtype == "embedding":
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(
                model=model, api_key=api_key or None, base_url=base_url or None,
                timeout=15, max_retries=1,
            )
            vec = await asyncio.to_thread(emb.embed_query, "连通性测试")
            if not isinstance(vec, (list, tuple)) or len(vec) == 0:
                raise RuntimeError("返回向量为空")
            detail = f"向量化成功，维度 {len(vec)}"
            if dim and len(vec) != int(dim):
                detail += f"（配置 dim={dim}，实际 {len(vec)}，请核对）"
        elif mtype == "rerank":
            import json as _json
            import urllib.request

            def _do():
                _body = _json.dumps(
                    {"model": model, "query": "连通性测试",
                     "documents": ["这是测试文档一", "这是测试文档二"]}
                ).encode("utf-8")
                req = urllib.request.Request(base_url, data=_body, method="POST")
                req.add_header("Content-Type", "application/json")
                if api_key:
                    req.add_header("Authorization", "Bearer " + api_key)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return _json.loads(resp.read().decode("utf-8"))

            _data = await asyncio.to_thread(_do)
            results = _data.get("results") or _data.get("data") or []
            detail = f"重排成功，返回 {len(results)} 条结果"
        else:
            return {"ok": False, "detail": f"不支持的类型: {mtype}", "latency_ms": 0}
    except Exception as e:  # noqa: BLE001
        err = str(e)
        if len(err) > 300:
            err = err[:300] + "…"
        return {"ok": False, "detail": err, "latency_ms": int((time.monotonic() - t0) * 1000)}
    return {"ok": True, "detail": detail, "latency_ms": int((time.monotonic() - t0) * 1000)}
