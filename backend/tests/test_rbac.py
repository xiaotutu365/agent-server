"""RBAC：角色 / 部门 CRUD 及与用户的关联——单元测试。

直接调用 agent.auth 的协程（即后台接口背后的实现），覆盖：
  - 启动时 seed 内置角色 admin/user，并 seed 管理员账号关联到 admin 角色
  - 角色：创建、重复 key 报错、删除内置角色报错、删除自定义角色成功
  - 部门：创建、删除
  - 用户：创建时关联 role_id / department_id；list_users 返回 role_name / department_name
  - 用户：更新角色 / 部门 / 密码（仅改密码不触碰部门）
  - 删除角色：其下用户回退为普通用户（role 归一为 user，role_id 指向 user 角色）
  - 删除部门：其下用户 department_id 置空

约定：与 test_mcp_gate.py 一致，用 asyncio.run 直接驱动协程，不依赖 pytest-asyncio / httpx。

运行：
  cd backend && ./venv/bin/python -m pytest tests/test_rbac.py -q
"""

import asyncio
import os

# 必须在 import agent.auth 之前固定管理员凭据，确保 seed_admin 出的账号可预测
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["JWT_SECRET"] = "test-secret-rbac"

import pytest

import agent.auth as auth


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    # auth.DB_PATH 是模块级常量（从 deep_agent 导入的绑定），monkeypatch 后
    # 所有 auth 协程将读写临时库，不影响真实 data/agent_sessions.db
    db = str(tmp_path / "rbac_test.db")
    monkeypatch.setattr(auth, "DB_PATH", db)
    return db


async def _init(tmp_db):
    await auth.init_users_table()
    await auth.init_roles_departments()
    await auth.seed_admin()


def test_seed_roles_and_admin(tmp_db):
    async def run():
        await _init(tmp_db)
        roles = await auth.list_roles()
        keys = {r["key"] for r in roles}
        assert {"admin", "user"} <= keys

        users = await auth.list_users()
        admin = next(u for u in users if u["username"] == "admin")
        assert admin["role"] == "admin"
        assert admin["role_id"] is not None
        role = await auth.get_role(admin["role_id"])
        assert role["key"] == "admin"
    asyncio.run(run())


def test_create_and_delete_role(tmp_db):
    async def run():
        await _init(tmp_db)
        r = await auth.create_role("经理", "manager", "部门负责人")
        assert r["key"] == "manager"
        assert any(x["id"] == r["id"] for x in await auth.list_roles())

        # 重复 key 报错
        with pytest.raises(ValueError):
            await auth.create_role("经理2", "manager")
        # 非法 key 报错
        with pytest.raises(ValueError):
            await auth.create_role("bad", "1bad")

        # 删除内置角色报错
        admin_role = await auth.get_role_by_key("admin")
        with pytest.raises(ValueError):
            await auth.delete_role(admin_role["id"])
        user_role = await auth.get_role_by_key("user")
        with pytest.raises(ValueError):
            await auth.delete_role(user_role["id"])

        # 删除自定义角色成功
        assert await auth.delete_role(r["id"]) is True
        assert await auth.get_role(r["id"]) is None
    asyncio.run(run())


def test_departments_crud(tmp_db):
    async def run():
        await _init(tmp_db)
        d = await auth.create_department("研发部", "desc")
        assert any(x["id"] == d["id"] for x in await auth.list_departments())
        assert await auth.delete_department(d["id"]) is True
        assert await auth.get_department(d["id"]) is None
    asyncio.run(run())


def test_user_role_department_association(tmp_db):
    async def run():
        await _init(tmp_db)
        user_role = await auth.get_role_by_key("user")
        dept = await auth.create_department("市场部")

        u = await auth.create_user("alice", "pw1234567", role_id=user_role["id"], department_id=dept["id"])
        assert u["role"] == "user"
        assert u["role_id"] == user_role["id"]
        assert u["department_id"] == dept["id"]

        # 管理员角色（key=admin）会让用户成为真管理员
        admin_role = await auth.get_role_by_key("admin")
        ad = await auth.create_user("root", "pw123456", role_id=admin_role["id"])
        assert ad["role"] == "admin"

        # list_users 返回关联名（LEFT JOIN）
        users = await auth.list_users()
        alice = next(x for x in users if x["id"] == u["id"])
        assert alice["role_name"] == "普通用户"
        assert alice["department_name"] == "市场部"
    asyncio.run(run())


def test_update_user_role_department_password(tmp_db):
    async def run():
        await _init(tmp_db)
        admin_role = await auth.get_role_by_key("admin")
        dept = await auth.create_department("财务部")

        u = await auth.create_user("bob", "pw123456")
        updated = await auth.update_user(
            u["id"], role_id=admin_role["id"], department_id=dept["id"], password="newpw123",
        )
        assert updated["role"] == "admin"
        assert updated["role_id"] == admin_role["id"]
        assert updated["department_id"] == dept["id"]
        assert await auth.verify_login("bob", "newpw123") is not None

        # 仅改密码不应触碰部门
        again = await auth.update_user(u["id"], password="newpw2123")
        assert again["department_id"] == dept["id"]
        assert await auth.verify_login("bob", "newpw2123") is not None
    asyncio.run(run())


def test_delete_role_cascades_user_to_user(tmp_db):
    async def run():
        await _init(tmp_db)
        # 自定义角色（key 非 admin/user）：创建用户时 role 被归一为 user，仅保留 role_id
        custom = await auth.create_role("临时", "temp")
        u = await auth.create_user("carol", "pw123456", role_id=custom["id"])
        assert u["role"] == "user"
        assert u["role_id"] == custom["id"]

        await auth.delete_role(custom["id"])
        refreshed = await auth.get_user(u["id"])
        user_role = await auth.get_role_by_key("user")
        assert refreshed["role"] == "user"
        assert refreshed["role_id"] == user_role["id"]
    asyncio.run(run())


def test_delete_department_nulls_user(tmp_db):
    async def run():
        await _init(tmp_db)
        dept = await auth.create_department("删除部")
        u = await auth.create_user("dave", "pw123456", department_id=dept["id"])
        assert u["department_id"] == dept["id"]

        await auth.delete_department(dept["id"])
        refreshed = await auth.get_user(u["id"])
        assert refreshed["department_id"] is None
    asyncio.run(run())
