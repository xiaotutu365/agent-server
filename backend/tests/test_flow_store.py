"""flow store 层测试：flows / flow_runs 两表 CRUD 与状态流转（SPEC-flow-config 3.1）。"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from flow import store  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    yield


@pytest.fixture()
def inited(tmp_db):
    asyncio.run(store.init_flow_tables())
    yield


DEF = {"nodes": [{"id": "n1", "type": "llm", "output_key": "draft"}], "edges": []}


def test_init_tables_idempotent(tmp_db):
    """建表幂等：连续两次初始化不抛错。"""
    asyncio.run(store.init_flow_tables())
    asyncio.run(store.init_flow_tables())


def test_flow_crud_roundtrip(inited):
    """创建 → 查询 → 列表 → 更新（version 自增）→ 删除。"""
    f = asyncio.run(store.create_flow("发布审核", DEF))
    assert f["flow_id"] and f["name"] == "发布审核"
    assert f["version"] == 1
    assert f["definition"] == DEF  # 返回时已解析为 dict
    assert f["created_at"] and f["updated_at"]

    got = asyncio.run(store.get_flow(f["flow_id"]))
    assert got == f

    assert [x["flow_id"] for x in asyncio.run(store.list_flows())] == [f["flow_id"]]

    updated = asyncio.run(store.update_flow(f["flow_id"], definition={"nodes": [], "edges": []}))
    assert updated["version"] == 2
    assert updated["definition"] == {"nodes": [], "edges": []}
    renamed = asyncio.run(store.update_flow(f["flow_id"], name="新名字"))
    assert renamed["name"] == "新名字"
    assert renamed["version"] == 3  # 任意更新都 bump version

    assert asyncio.run(store.delete_flow(f["flow_id"])) is True
    assert asyncio.run(store.get_flow(f["flow_id"])) is None
    assert asyncio.run(store.delete_flow(f["flow_id"])) is False


def test_update_missing_flow_returns_none(inited):
    assert asyncio.run(store.update_flow("no-such", name="x")) is None


def test_run_lifecycle(inited):
    """run 状态流转：running → waiting_human → done，outputs 逐节点累积。"""
    f = asyncio.run(store.create_flow("发布审核", DEF))
    run = asyncio.run(store.create_run(f["flow_id"], {"topic": "Q3 计划"}))
    assert run["run_id"] and run["flow_id"] == f["flow_id"]
    assert run["status"] == "running"
    assert run["input"] == {"topic": "Q3 计划"}
    assert run["outputs"] == {}
    assert run["error"] is None

    asyncio.run(store.update_run(run["run_id"], status="waiting_human", current_node="review"))
    got = asyncio.run(store.get_run(run["run_id"]))
    assert got["status"] == "waiting_human"
    assert got["current_node"] == "review"

    asyncio.run(store.update_run(run["run_id"], status="done", outputs={"draft": "初稿"}))
    got = asyncio.run(store.get_run(run["run_id"]))
    assert got["status"] == "done"
    assert got["outputs"] == {"draft": "初稿"}


def test_run_failed_and_cancelled(inited):
    """failed 携带 error；cancel 置状态。"""
    f = asyncio.run(store.create_flow("f", DEF))
    r1 = asyncio.run(store.create_run(f["flow_id"], {}))
    asyncio.run(store.update_run(r1["run_id"], status="failed", error="LLM 超时"))
    got = asyncio.run(store.get_run(r1["run_id"]))
    assert got["status"] == "failed" and got["error"] == "LLM 超时"

    r2 = asyncio.run(store.create_run(f["flow_id"], {}))
    asyncio.run(store.update_run(r2["run_id"], status="cancelled"))
    assert asyncio.run(store.get_run(r2["run_id"]))["status"] == "cancelled"


def test_list_runs_filter_by_flow(inited):
    """list_runs 按 flow_id 过滤，最新在前。"""
    f1 = asyncio.run(store.create_flow("a", DEF))
    f2 = asyncio.run(store.create_flow("b", DEF))
    r1 = asyncio.run(store.create_run(f1["flow_id"], {}))
    r2 = asyncio.run(store.create_run(f1["flow_id"], {}))
    asyncio.run(store.create_run(f2["flow_id"], {}))

    runs = asyncio.run(store.list_runs(f1["flow_id"]))
    assert [r["run_id"] for r in runs] == [r2["run_id"], r1["run_id"]]
    assert len(asyncio.run(store.list_runs())) == 3


def test_get_missing_run_returns_none(inited):
    assert asyncio.run(store.get_run("no-such")) is None
