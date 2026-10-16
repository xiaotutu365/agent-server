"""回归测试：服务端退出（token 黑名单）。

背景：此前后端只有 /api/auth/login，前端「退出登录」仅清 localStorage，
JWT 在 exp（7 天）前仍然有效，拿到 token 即可继续调用所有接口。
新增 POST /api/auth/logout 后，已登出的 token 必须被 get_current_user 拒绝，
且不影响同一用户的其他 token。

运行：
  cd backend && ./venv/Scripts/python.exe -m pytest tests/test_auth_logout.py -q
"""

import asyncio
import os

# 必须在 import agent.auth 之前固定管理员凭据，确保 seed_admin 出的账号可预测
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["JWT_SECRET"] = "test-secret-logout"

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import agent.auth as auth


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "logout_test.db")
    monkeypatch.setattr(auth, "DB_PATH", db)
    auth._REVOKED.clear()
    yield db
    auth._REVOKED.clear()


def _creds(token: str):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def _init():
    await auth.init_users_table()
    await auth.init_roles_departments()
    await auth.seed_admin()


def test_logout_revokes_token(tmp_db):
    """登出后旧 token 调 get_current_user 应 401；登出前可用。"""
    async def run():
        await _init()
        user = await auth.verify_login("admin", "admin123")
        token = auth.encode_token(user)

        u = await auth.get_current_user(_creds(token))
        assert u["username"] == "admin"

        await auth.logout_token(token)
        with pytest.raises(HTTPException) as ei:
            await auth.get_current_user(_creds(token))
        assert ei.value.status_code == 401
    asyncio.run(run())


def test_other_tokens_unaffected(tmp_db):
    """吊销某 token 不应影响其他用户/其他 token。"""
    async def run():
        await _init()
        user_role = await auth.get_role_by_key("user")
        alice = await auth.create_user("alice", "pw123456", role_id=user_role["id"])

        admin_token = auth.encode_token(await auth.verify_login("admin", "admin123"))
        alice_token = auth.encode_token(alice)

        await auth.logout_token(admin_token)
        u = await auth.get_current_user(_creds(alice_token))
        assert u["username"] == "alice"
    asyncio.run(run())


def test_logout_endpoint(tmp_db):
    """POST /api/auth/logout 处理当前 Bearer token。"""
    import main

    async def run():
        await _init()
        token = auth.encode_token(await auth.verify_login("admin", "admin123"))
        resp = await main.logout(_creds(token))
        assert resp == {"ok": True}
        with pytest.raises(HTTPException) as ei:
            await auth.get_current_user(_creds(token))
        assert ei.value.status_code == 401
    asyncio.run(run())


def test_logout_without_token_is_noop(tmp_db):
    """未携带凭证时登出应幂等成功，不报错。"""
    import main

    async def run():
        resp = await main.logout(None)
        assert resp == {"ok": True}
    asyncio.run(run())
