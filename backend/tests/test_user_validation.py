"""回归测试：新增用户的字段校验与扩展字段（邮箱 / 电话 / 姓名）。

覆盖：
  - 用户名：2–32 位字母/数字/下划线/连字符；非法格式报 ValueError
  - 密码：6–64 位且同时包含字母和数字
  - 邮箱：可选；格式校验；归一化（trim + 小写）；唯一（重复报错）
  - 电话：可选；宽松格式（可含 +、空格、连字符、括号）
  - 姓名：可选；≤50 字符
  - create_user 返回扩展字段；update_user 可修改/清空（空串=清空）

运行：
  cd backend && ./venv/Scripts/python.exe -m pytest tests/test_user_validation.py -q
"""

import asyncio
import os

os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["JWT_SECRET"] = "test-secret-uv"

import pytest

import agent.auth as auth


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "uv_test.db")
    monkeypatch.setattr(auth, "DB_PATH", db)
    return db


async def _init():
    await auth.init_users_table()
    await auth.init_roles_departments()
    await auth.seed_admin()


def _run(fn):
    asyncio.run(fn())


def test_create_user_with_extra_fields(tmp_db):
    async def run():
        await _init()
        u = await auth.create_user(
            "alice", "abc123",
            email="  Alice@Example.COM ", phone="+86 138-0013-8000", full_name=" 张三 ",
        )
        assert u["email"] == "alice@example.com"
        assert u["phone"] == "+86 138-0013-8000"
        assert u["full_name"] == "张三"
        # 列表接口同样返回扩展字段
        listed = next(x for x in await auth.list_users() if x["id"] == u["id"])
        assert listed["email"] == "alice@example.com"
    _run(run)


def test_invalid_username_rejected(tmp_db):
    async def run():
        await _init()
        for bad in ["", "a", "用", "bad name", "bad@name", "u" * 33]:
            with pytest.raises(ValueError):
                await auth.create_user(bad, "abc123")
        # 合法边界
        await auth.create_user("ab", "abc123")
        await auth.create_user("u" * 32, "abc123")
    _run(run)


def test_weak_password_rejected(tmp_db):
    async def run():
        await _init()
        for bad in ["", "123", "abcdefgh", "12345678", "ab1"]:
            with pytest.raises(ValueError):
                await auth.create_user("bob", bad)
        await auth.create_user("bob", "abc123")
    _run(run)


def test_invalid_email_rejected(tmp_db):
    async def run():
        await _init()
        for bad in ["abc", "a@b", "a b@c.com", "@c.com", "a@.com"]:
            with pytest.raises(ValueError):
                await auth.create_user("carol", "abc123", email=bad)
        # 可选：留空不报错
        u = await auth.create_user("carol", "abc123", email="")
        assert u["email"] is None
    _run(run)


def test_duplicate_email_rejected(tmp_db):
    async def run():
        await _init()
        await auth.create_user("dave", "abc123", email="dave@x.com")
        with pytest.raises(ValueError):
            await auth.create_user("erin", "abc123", email="DAVE@x.com")
    _run(run)


def test_invalid_phone_rejected(tmp_db):
    async def run():
        await _init()
        for bad in ["abc", "1234", "1380013800000000000000"]:
            with pytest.raises(ValueError):
                await auth.create_user("frank", "abc123", phone=bad)
        await auth.create_user("frank", "abc123", phone="13800138000")
    _run(run)


def test_full_name_length_limit(tmp_db):
    async def run():
        await _init()
        with pytest.raises(ValueError):
            await auth.create_user("grace", "abc123", full_name="名" * 51)
    _run(run)


def test_update_user_extra_fields(tmp_db):
    async def run():
        await _init()
        u = await auth.create_user("heidi", "abc123", email="heidi@x.com")
        upd = await auth.update_user(u["id"], email="new@x.com", phone="13900139000", full_name="海蒂")
        assert upd["email"] == "new@x.com"
        assert upd["phone"] == "13900139000"
        assert upd["full_name"] == "海蒂"
        # 空串 = 清空
        upd2 = await auth.update_user(u["id"], email="")
        assert upd2["email"] is None
        # 非法值被拒
        with pytest.raises(ValueError):
            await auth.update_user(u["id"], email="bad-email")
        # None 表示不修改
        upd3 = await auth.update_user(u["id"], phone=None)
        assert upd3["phone"] == "13900139000"
    _run(run)
