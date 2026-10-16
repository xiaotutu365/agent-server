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
import re
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


# ---------- 登出黑名单（内存态；token 自然过期后随之清理） ----------
_REVOKED: dict[str, int] = {}  # token -> exp（unix 秒）


async def logout_token(token: str) -> None:
    """将 token 加入黑名单；顺带清理已过期条目，避免字典无限增长。"""
    payload = decode_token(token)
    exp = payload.get("exp", 0) if payload else 0
    now = int(time.time())
    for k in [k for k, v in _REVOKED.items() if v <= now]:
        _REVOKED.pop(k, None)
    _REVOKED[token] = max(exp, now)


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
    # 确保 DB 文件所在目录存在（全新检出时 data/ 可能尚不存在，否则 connect 会失败）
    _db_dir = os.path.dirname(DB_PATH)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)
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
        for col in ("role_id TEXT", "department_id TEXT",
                    "email TEXT", "phone TEXT", "full_name TEXT"):
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception:
                pass
        # 邮箱唯一（仅非空值参与约束）
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email "
            "ON users(email) WHERE email IS NOT NULL AND email <> ''"
        )
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


def _cell(row, key, default=None):
    """安全读取 sqlite3.Row 中的列：缺失时返回 default（sqlite3.Row 无 .get）。"""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "role_id": row["role_id"],
        "role_name": _cell(row, "role_name"),
        "department_id": row["department_id"],
        "department_name": _cell(row, "department_name"),
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "email": _cell(row, "email"),
        "phone": _cell(row, "phone"),
        "full_name": _cell(row, "full_name"),
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


# ---------- 字段校验（服务端为准；前端沿用同一规则做即时反馈） ----------
_USERNAME_RE = re.compile(r"[a-zA-Z0-9_-]{2,32}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE = re.compile(r"\+?\d{5,15}")


def _validate_username(username: str) -> str:
    name = (username or "").strip()
    if not name:
        raise ValueError("用户名不能为空")
    if not _USERNAME_RE.fullmatch(name):
        raise ValueError("用户名需为 2–32 位字母、数字、下划线或连字符")
    return name


def _validate_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空")
    if len(password) < 6 or len(password) > 64:
        raise ValueError("密码长度需为 6–64 位")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("密码需同时包含字母和数字")
    return password


def _validate_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    if not e:
        return None
    if len(e) > 254 or not _EMAIL_RE.fullmatch(e):
        raise ValueError("邮箱格式不正确")
    return e


def _validate_phone(phone: str | None) -> str | None:
    p = (phone or "").strip()
    if not p:
        return None
    if not _PHONE_RE.fullmatch(re.sub(r"[\s\-()]", "", p)):
        raise ValueError("电话格式不正确（可含 +、数字、空格、连字符、括号）")
    return p


def _validate_full_name(full_name: str | None) -> str | None:
    n = (full_name or "").strip()
    if not n:
        return None
    if len(n) > 50:
        raise ValueError("姓名不能超过 50 个字符")
    return n


async def create_user(
    username: str,
    password: str,
    role: str = "user",
    role_id: str | None = None,
    department_id: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
) -> dict:
    username = _validate_username(username)
    password = _validate_password(password)
    email = _validate_email(email)
    phone = _validate_phone(phone)
    full_name = _validate_full_name(full_name)
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
    if email:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT id FROM users WHERE email=?", (email,))
            if await cur.fetchone():
                raise ValueError("邮箱已被使用")
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute(
                "INSERT INTO users (id,username,password_hash,role,role_id,department_id,"
                "email,phone,full_name,disabled,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), username, _hash_password(password), role, role_id,
                 department_id, email, phone, full_name, 0,
                 datetime.now(timezone.utc).isoformat()),
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
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
) -> dict | None:
    # None=不修改；空串=清空（email/phone/full_name）
    if password:
        password = _validate_password(password)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            return None
        # 先归一化再查重：""→None（清空），None→保留原值
        new_email = _validate_email(email) if email is not None else _cell(row, "email")
        new_phone = _validate_phone(phone) if phone is not None else _cell(row, "phone")
        new_full_name = _validate_full_name(full_name) if full_name is not None else _cell(row, "full_name")
        if new_email:
            c = await conn.execute("SELECT id FROM users WHERE email=? AND id<>?", (new_email, uid))
            if await c.fetchone():
                raise ValueError("邮箱已被使用")
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
            "UPDATE users SET role=?, role_id=?, department_id=?, password_hash=?, "
            "email=?, phone=?, full_name=? WHERE id=?",
            (new_role, new_role_id, new_dept, new_pw, new_email, new_phone, new_full_name, uid),
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
    if creds.credentials in _REVOKED:
        raise HTTPException(status_code=401, detail="已登出，请重新登录")
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
