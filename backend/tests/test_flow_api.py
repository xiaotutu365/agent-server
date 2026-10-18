"""flow API 契约测试（SPEC-flow-config 3.4）：8 端点 + SSE 事件流。

鉴权按 test_memory_api 模式用 dependency_overrides 打桩；agent 工厂与
checkpointer 打桩为 FakeAgent + InMemorySaver，后台执行脱离请求返回。
"""

import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

import agent.auth
from flow import api as flow_api
from flow import store

ADMIN = {"id": "admin-1", "role": "admin", "username": "admin"}
USER = {"id": "u1", "role": "user", "username": "zhang"}


class FakeAgent:
    async def ainvoke(self, inputs, config=None):
        return {"messages": list(inputs["messages"]) + [
            {"role": "assistant", "content": "初稿内容"}]}


async def fake_factory(node):
    return FakeAgent()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    asyncio.run(store.init_flow_tables())
    monkeypatch.setattr(flow_api, "_agent_factory", fake_factory)

    cp = InMemorySaver()  # 同一实例贯穿 start/resume（模拟生产单例）

    async def fake_cp():
        return cp

    monkeypatch.setattr(flow_api, "_get_checkpointer", fake_cp)
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(flow_api.router)
    app.dependency_overrides[agent.auth.require_admin] = lambda: ADMIN
    app.dependency_overrides[agent.auth.get_current_user] = lambda: USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def linear_definition() -> dict:
    return {
        "entry": "generate",
        "nodes": [
            {"id": "generate", "type": "llm", "output_key": "draft",
             "agent": {"system_prompt": "作者"}, "input": "主题：${input.topic}"},
            {"id": "calc", "type": "tool", "output_key": "result",
             "tool": "calculator", "args": {"expression": "1+1"}},
        ],
        "edges": [{"from": "generate", "to": "calc"}],
    }


def review_definition() -> dict:
    return {
        "entry": "generate",
        "nodes": [
            {"id": "generate", "type": "llm", "output_key": "draft",
             "agent": {"system_prompt": "作者"}},
            {"id": "review", "type": "human", "output_key": "decision",
             "prompt": "请审批初稿"},
            {"id": "calc", "type": "tool", "output_key": "result",
             "tool": "calculator", "args": {"expression": "1+1"}},
        ],
        "edges": [
            {"from": "generate", "to": "review"},
            {"from": "review", "to": "calc", "when": "approved"},
            {"from": "review", "to": "generate", "when": "rejected"},
        ],
    }


def create_flow(client, name="线性", definition=None):
    r = client.post("/api/flows", json={
        "name": name, "definition": definition or linear_definition()})
    assert r.status_code == 200, r.text
    return r.json()["flow"]


def wait_run(client, run_id, wanted, timeout=10.0):
    deadline = time.time() + timeout
    run = None
    while time.time() < deadline:
        run = client.get(f"/api/flow-runs/{run_id}").json()["run"]
        if run["status"] in wanted:
            return run
        time.sleep(0.05)
    raise AssertionError(f"超时等待 {wanted}，最后状态 {run['status']} error={run['error']}")


def wait_updated(client, run_id, updated_at_before, wanted, timeout=15.0):
    """等待实例落到 wanted 且 updated_at 晚于前值（确认本段执行真正落了新状态）。

    FakeAgent 下整段执行（resume→重跑→重新挂起/终态）仅几毫秒，快于轮询间隔，
    中间态 running 不可观察——「旧暂停」与「新暂停」都呈 waiting_human，
    故以 updated_at 是否变化判别（真挂起则永不变化，超时并给出前值对照）。
    """
    deadline = time.time() + timeout
    run = None
    while time.time() < deadline:
        run = client.get(f"/api/flow-runs/{run_id}").json()["run"]
        if run["status"] in wanted and run["updated_at"] != updated_at_before:
            return run
        time.sleep(0.05)
    raise AssertionError(f"超时等待 {wanted}，最后状态 {run['status']} "
                         f"error={run['error']} updated_at={run['updated_at']} "
                         f"(前值 {updated_at_before})")


def resume_and_wait(client, run_id, body, wanted, timeout=15.0):
    before = client.get(f"/api/flow-runs/{run_id}").json()["run"]["updated_at"]
    r = client.post(f"/api/flow-runs/{run_id}/resume", json=body)
    assert r.status_code == 200, r.text
    return wait_updated(client, run_id, before, wanted, timeout)


# ---------- 流程 CRUD（管理员） ----------

def test_flow_crud_and_validation(client):
    f = create_flow(client)
    assert f["version"] == 1 and f["name"] == "线性"

    assert [x["flow_id"] for x in client.get("/api/flows").json()["flows"]] == [f["flow_id"]]
    assert client.get(f"/api/flows/{f['flow_id']}").json()["flow"] == f

    # 非法 definition → 400 且错误带字段路径
    bad = linear_definition()
    bad["nodes"][0]["type"] = "magic"
    r = client.post("/api/flows", json={"name": "bad", "definition": bad})
    assert r.status_code == 400
    assert "nodes[0].type" in r.json()["detail"]

    # 更新 bump version
    r = client.put(f"/api/flows/{f['flow_id']}", json={"name": "线性v2"})
    assert r.status_code == 200 and r.json()["flow"]["version"] == 2

    assert client.delete(f"/api/flows/{f['flow_id']}").status_code == 200
    assert client.get(f"/api/flows/{f['flow_id']}").status_code == 404
    assert client.delete(f"/api/flows/{f['flow_id']}").status_code == 404


def test_update_flow_validates_definition(client):
    f = create_flow(client)
    bad = linear_definition()
    del bad["entry"]
    r = client.put(f"/api/flows/{f['flow_id']}", json={"definition": bad})
    assert r.status_code == 400 and "definition.entry" in r.json()["detail"]


# ---------- 发起 / 实例查询 / 人审 / 取消 ----------

def test_start_run_executes_to_done(client):
    f = create_flow(client)
    r = client.post(f"/api/flows/{f['flow_id']}/runs", json={"input": {"topic": "Q3"}})
    assert r.status_code == 200
    run_id = r.json()["run"]["run_id"]

    run = wait_run(client, run_id, {"done", "failed"})
    assert run["status"] == "done"
    assert run["outputs"]["result"] == "1+1 = 2"

    runs = client.get("/api/flow-runs", params={"flow_id": f["flow_id"]}).json()["runs"]
    assert [x["run_id"] for x in runs] == [run_id]


def test_start_run_missing_flow_404(client):
    assert client.post("/api/flows/no-such/runs", json={"input": {}}).status_code == 404


def test_human_review_pause_resume_and_outputs(client):
    f = create_flow(client, "审批", review_definition())
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {"topic": "t"}}).json()["run"]["run_id"]

    run = wait_run(client, run_id, {"waiting_human", "failed"})
    assert run["status"] == "waiting_human"

    detail = client.get(f"/api/flow-runs/{run_id}").json()
    assert detail["pending"] == {"node": "review", "prompt": "请审批初稿",
                                 "output_key": "decision"}

    run = resume_and_wait(client, run_id, {"decision": "approved", "comment": "ok"},
                          {"done", "failed"})
    assert run["status"] == "done"
    assert run["outputs"]["result"] == "1+1 = 2"
    assert client.get(f"/api/flow-runs/{run_id}").json()["pending"] is None


def test_resume_rejected_then_done(client):
    f = create_flow(client, "审批", review_definition())
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"waiting_human"})

    run = resume_and_wait(client, run_id, {"decision": "rejected"},
                          {"waiting_human", "done", "failed"})
    assert run["status"] == "waiting_human"  # 回到人审点

    resume_and_wait(client, run_id, {"decision": "approved"}, {"done", "failed"})
    assert client.get(f"/api/flow-runs/{run_id}").json()["run"]["status"] == "done"


def test_resume_run_not_waiting_400(client):
    f = create_flow(client)
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"done"})
    r = client.post(f"/api/flow-runs/{run_id}/resume", json={"decision": "approved"})
    assert r.status_code == 400


def test_resume_while_inflight_rejected(client, monkeypatch):
    """上一段执行未结束时不允许再次 resume（防并发恢复破坏图状态）。"""

    class SlowAgent:
        async def ainvoke(self, inputs, config=None):
            await asyncio.sleep(0.5)
            return {"messages": list(inputs["messages"]) + [
                {"role": "assistant", "content": "初稿内容"}]}

    async def slow_factory(node):
        return SlowAgent()

    monkeypatch.setattr(flow_api, "_agent_factory", slow_factory)

    f = create_flow(client, "审批", review_definition())
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"waiting_human"})

    before = client.get(f"/api/flow-runs/{run_id}").json()["run"]["updated_at"]
    r = client.post(f"/api/flow-runs/{run_id}/resume", json={"decision": "rejected"})
    assert r.status_code == 200
    # 执行窗口内（llm 睡 0.5s）再来一次恢复 → 400
    r2 = client.post(f"/api/flow-runs/{run_id}/resume", json={"decision": "rejected"})
    assert r2.status_code == 400
    assert "正在执行" in r2.json()["detail"]

    run = wait_updated(client, run_id, before, {"waiting_human", "done", "failed"})
    assert run["status"] == "waiting_human"  # 第一段恢复正常回到人审点


def test_cancel_waiting_run(client):
    f = create_flow(client, "审批", review_definition())
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"waiting_human"})
    r = client.post(f"/api/flow-runs/{run_id}/cancel")
    assert r.status_code == 200
    assert client.get(f"/api/flow-runs/{run_id}").json()["run"]["status"] == "cancelled"


# ---------- SSE 进度流 ----------

def _parse_sse(lines):
    events = []
    cur = {}
    for line in lines:
        if line.startswith("event: "):
            cur["event"] = line[len("event: "):]
        elif line.startswith("data: ") and cur.get("event"):
            cur["data"] = json.loads(line[len("data: "):])
            events.append(cur)
            cur = {}
    return events


def test_stream_done_run_snapshot(client):
    f = create_flow(client)
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"done"})

    with client.stream("GET", f"/api/flow-runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        events = _parse_sse([l for l in resp.iter_lines()])
    kinds = [e["event"] for e in events]
    assert kinds[0] == "flow_status"
    assert events[0]["data"]["status"] == "done"
    assert kinds[-1] == "done"


def test_stream_waiting_run_closes_after_status(client):
    f = create_flow(client, "审批", review_definition())
    run_id = client.post(f"/api/flows/{f['flow_id']}/runs",
                         json={"input": {}}).json()["run"]["run_id"]
    wait_run(client, run_id, {"waiting_human"})

    with client.stream("GET", f"/api/flow-runs/{run_id}/stream") as resp:
        events = _parse_sse([l for l in resp.iter_lines()])
    assert events[0]["data"]["status"] == "waiting_human"
    assert events[-1]["event"] == "done"
    assert "flow_step" in [e["event"] for e in events]  # 回放历史节点事件


def test_stream_missing_run_error_event(client):
    with client.stream("GET", "/api/flow-runs/no-such/stream") as resp:
        events = _parse_sse([l for l in resp.iter_lines()])
    assert events[0]["event"] == "error"
