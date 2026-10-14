"""认证与用户管理（JWT，无第三方依赖；密码用 PBKDF2-HMAC-SHA256）。

用户表 users 存于 data/agent_sessions.db（与配置/会话同库）。
角色：admin（可进后台 + 用户管理）/ user（仅前台聊天）。
首次启动 seed 一个管理员（账号见 seed_admin，可用环境变量覆盖）。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent.deep_agent import DB_PATH

SECRET = os.getenv("JWT_SECRET", "deepagent-dev-secret-change-me")
ALGO = "HS256"
TOKEN_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", "604800"))  # 7 天

_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

_bearer = HTTPBearer(auto_error=False)


# ---------- 密码哈希 ----------
def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return f"pbkdf2_sha256$100000${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(base64.b64encode(dk).decode(), hash_b64)
    except Exception:
        return False


# ---------- JWT（HS256，自实现，避免外部依赖） ----------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def encode_token(user: dict) -> str:
    header = {"alg": ALGO, "typ": "JWT"}
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "role": user["role"],
        "exp": int(time.time()) + TOKEN_EXP_SECONDS,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = _b64url(hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        h, p, s = token.split(".")
        signing_input = f"{h}.{p}".encode()
        expected = _b64url(hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, s):
            return None
        payload = json.loads(_b64url_decode(p).decode())
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# ---------- 用户表 ----------
async def init_users_table():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )"""
        )
        await conn.commit()


async def seed_admin():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
        if (await cur.fetchone())["c"] > 0:
            return
        await conn.execute(
            "INSERT INTO users (id,username,password_hash,role,disabled,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), _ADMIN_USERNAME, _hash_password(_ADMIN_PASSWORD),
             "admin", 0, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
    }


async def get_user(uid: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
    return _row_to_user(row) if row else None


async def verify_login(username: str, password: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE username=?", (username,))
        row = await cur.fetchone()
    if not row or bool(row["disabled"]):
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


async def create_user(username: str, password: str, role: str = "user") -> dict:
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if role not in ("admin", "user"):
        role = "user"
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute(
                "INSERT INTO users (id,username,password_hash,role,disabled,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), username, _hash_password(password), role, 0,
                 datetime.now(timezone.utc).isoformat()),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise ValueError("用户名已存在")
    u = await get_user_by_username(username)
    return u


async def get_user_by_username(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE username=?", (username,))
        row = await cur.fetchone()
    return _row_to_user(row) if row else None


async def list_users() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = await cur.fetchall()
    return [_row_to_user(r) for r in rows]


async def delete_user(uid: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            return False
        if row["role"] == "admin":
            c = await conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'")
            if (await c.fetchone())["c"] <= 1:
                raise ValueError("至少保留一个管理员，无法删除")
        await conn.execute("DELETE FROM users WHERE id=?", (uid,))
        await conn.commit()
    return True


# ---------- 鉴权依赖 ----------
async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="未登录或缺少凭证")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="凭证无效或已过期")
    user = await get_user(payload["sub"])
    if not user or user["disabled"]:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
