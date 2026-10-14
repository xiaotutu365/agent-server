"""认证与用户管理（JWT，无第三方依赖；密码用 PBKDF2-HMAC-SHA256）。

用户表 users 存于 data/agent_sessions.db（与配置/会话同库）。
角色现由 roles 表统一管理；users.role 仍保留角色 key（admin/user/...）以兼容鉴权，
users.role_id 关联 roles.id。系统管理另含 departments 表，users.department_id 关联之。
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


# ---------- 角色 / 部门 表 ----------
async def init_roles_departments():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS departments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        await conn.commit()
    await seed_roles()


async def seed_roles():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT COUNT(*) AS c FROM roles")
        if (await cur.fetchone())["c"] > 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "INSERT INTO roles (id,name,key,description,created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "管理员", "admin", "可进入后台并进行所有管理操作", now),
        )
        await conn.execute(
            "INSERT INTO roles (id,name,key,description,created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "普通用户", "user", "仅前台对话，无后台权限", now),
        )
        await conn.commit()


async def list_roles() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM roles ORDER BY created_at ASC")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_role(rid: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM roles WHERE id=?", (rid,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_role_by_key(key: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM roles WHERE key=?", (key,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_role(name: str, key: str, description: str = "") -> dict:
    if not name or not key:
        raise ValueError("角色名称和 key 不能为空")
    key = key.strip()
    if not key.isidentifier():
        raise ValueError("角色 key 需为合法标识符（字母/数字/下划线，且不以数字开头）")
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute(
                "INSERT INTO roles (id,name,key,description,created_at) VALUES (?,?,?,?,?)",
                (rid, name.strip(), key, description or "", now),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise ValueError("角色 key 已存在")
    return {"id": rid, "name": name.strip(), "key": key, "description": description or "", "created_at": now}


async def delete_role(rid: str):
    role = await get_role(rid)
    if not role:
        return False
    if role["key"] in ("admin", "user"):
        raise ValueError("不能删除内置角色（admin / user）")
    async with aiosqlite.connect(DB_PATH) as conn:
        # 该角色下的用户回退为普通用户
        user_role = await get_role_by_key("user")
        if user_role:
            await conn.execute(
                "UPDATE users SET role_id=?, role=? WHERE role_id=?",
                (user_role["id"], "user", rid),
            )
        await conn.execute("DELETE FROM roles WHERE id=?", (rid,))
        await conn.commit()
    return True


async def list_departments() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM departments ORDER BY created_at ASC")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_department(did: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM departments WHERE id=?", (did,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_department(name: str, description: str = "") -> dict:
    if not name:
        raise ValueError("部门名称不能为空")
    did = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO departments (id,name,description,created_at) VALUES (?,?,?,?)",
            (did, name.strip(), description or "", now),
        )
        await conn.commit()
    return {"id": did, "name": name.strip(), "description": description or "", "created_at": now}


async def delete_department(did: str):
    if not await get_department(did):
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET department_id=NULL WHERE department_id=?", (did,))
        await conn.execute("DELETE FROM departments WHERE id=?", (did,))
        await conn.commit()
    return True


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
                created_at TEXT NOT NULL,
                role_id TEXT,
                department_id TEXT
            )"""
        )
        # 兼容已存在的旧表：补列（已存在则忽略错误）
        for col in ("role_id TEXT", "department_id TEXT"):
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception:
                pass
        await conn.commit()


async def seed_admin():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
        if (await cur.fetchone())["c"] > 0:
            return
        admin_role = await get_role_by_key("admin")
        role_id = admin_role["id"] if admin_role else None
        await conn.execute(
            "INSERT INTO users (id,username,password_hash,role,role_id,disabled,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), _ADMIN_USERNAME, _hash_password(_ADMIN_PASSWORD),
             "admin", role_id, 0, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "role_id": row["role_id"],
        "role_name": row.get("role_name"),
        "department_id": row["department_id"],
        "department_name": row.get("department_name"),
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


async def create_user(
    username: str,
    password: str,
    role: str = "user",
    role_id: str | None = None,
    department_id: str | None = None,
) -> dict:
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    # 以 role_id 为准解析角色 key；未给则回退到 role 字符串
    if role_id:
        r = await get_role(role_id)
        if r:
            role = r["key"]
    if role not in ("admin", "user"):
        role = "user"
    if role_id is None:
        ar = await get_role_by_key(role)
        role_id = ar["id"] if ar else None
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute(
                "INSERT INTO users (id,username,password_hash,role,role_id,department_id,disabled,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), username, _hash_password(password), role, role_id,
                 department_id, 0, datetime.now(timezone.utc).isoformat()),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise ValueError("用户名已存在")
    return await get_user_by_username(username)


async def update_user(
    uid: str,
    role: str | None = None,
    role_id: str | None = None,
    department_id: str | None = None,
    password: str | None = None,
) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            return None
        if role_id is not None:
            r = await get_role(role_id)
            role = r["key"] if r else row["role"]
        new_role = role if role is not None else row["role"]
        if new_role not in ("admin", "user"):
            new_role = row["role"]
        new_role_id = role_id if role_id is not None else row["role_id"]
        if new_role_id is None:
            ar = await get_role_by_key(new_role)
            new_role_id = ar["id"] if ar else None
        new_dept = department_id if department_id is not None else row["department_id"]
        new_pw = _hash_password(password) if password else row["password_hash"]
        await conn.execute(
            "UPDATE users SET role=?, role_id=?, department_id=?, password_hash=? WHERE id=?",
            (new_role, new_role_id, new_dept, new_pw, uid),
        )
        await conn.commit()
    return await get_user(uid)


async def get_user_by_username(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE username=?", (username,))
        row = await cur.fetchone()
    return _row_to_user(row) if row else None


async def list_users() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT u.*, r.name AS role_name, d.name AS department_name
               FROM users u
               LEFT JOIN roles r ON u.role_id = r.id
               LEFT JOIN departments d ON u.department_id = d.id
               ORDER BY u.created_at DESC"""
        )
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
