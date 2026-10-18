"""流程 API（SPEC-flow-config 3.4）。

- 流程 CRUD（管理员）：/api/flows
- 发起 / 实例查询 / 人审 / 取消 / SSE（登录用户）：/api/flows/{id}/runs、/api/flow-runs/*
- 发起与恢复均为脱离执行（后台任务），进度经事件总线进入 SSE；
  事件先落历史缓冲（_EVENT_LOGS），SSE 连接先回放再跟随，杜绝丢事件
"""

import asyncio
import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from agent.auth import get_current_user, require_admin
from agent.deep_agent import DB_PATH
from flow import dsl, runner, store

router = APIRouter(prefix="/api")

TERMINAL_STATUSES = {"done", "failed", "cancelled"}

# —— 事件总线：run_id → 历史事件 / 订阅者队列；后台任务集合 ——
_EVENT_LOGS: dict[str, list] = {}
_EVENT_QUEUES: dict[str, list] = {}
_BG_TASKS: set = set()
_INFLIGHT: set[str] = set()  # 正在后台执行的实例（防并发 resume 破坏图状态）

# —— agent 工厂缓存（节点级 system_prompt/kb_ids/tools/model_id 组合）——
_AGENT_CACHE: dict = {}
_FACTORY_LOCK: asyncio.Lock | None = None
_checkpointer = None


class FlowBody(BaseModel):
    name: str
    definition: dict


class FlowUpdateBody(BaseModel):
    name: str | None = None
    definition: dict | None = None


class RunBody(BaseModel):
    input: dict = {}


async def _get_checkpointer():
    """流程图专用 checkpointer（与聊天同库，人审暂停可跨进程恢复）。"""
    global _checkpointer
    if _checkpointer is None:
        conn = await aiosqlite.connect(DB_PATH)
        cp = AsyncSqliteSaver(conn)
        await cp.setup()
        _checkpointer = cp
    return _checkpointer


async def _agent_factory(node: dict):
    """llm 节点 → deep agent：按节点配置组合缓存构建（复用全局默认配置为基底）。"""
    a = node.get("agent") or {}
    key = json.dumps([a.get("system_prompt"), sorted(a.get("kb_ids") or []),
                      sorted(a.get("tools") or []), a.get("model_id") or ""],
                     ensure_ascii=False)
    if key in _AGENT_CACHE:
        return _AGENT_CACHE[key]
    global _FACTORY_LOCK
    if _FACTORY_LOCK is None:
        _FACTORY_LOCK = asyncio.Lock()
    async with _FACTORY_LOCK:
        if key in _AGENT_CACHE:
            return _AGENT_CACHE[key]
        from agent.config_store import load_default_config
        from agent.deep_agent import build_agent

        cfg = await load_default_config()
        cfg["system_prompt"] = a.get("system_prompt") or cfg.get("system_prompt", "")
        if a.get("kb_ids") is not None:
            cfg["kb_ids"] = a["kb_ids"]
            cfg["kb_enabled"] = bool(a["kb_ids"])
        if a.get("tools"):
            cfg["tools_enabled"] = a["tools"]
        agent = await build_agent(cfg, model_id=a.get("model_id") or None)
        _AGENT_CACHE[key] = agent
        return agent


async def _publish(run_id: str, event: dict):
    _EVENT_LOGS.setdefault(run_id, []).append(event)
    for q in _EVENT_QUEUES.get(run_id, []):
        await q.put(event)


def _spawn(coro):
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def _execute_detached(run: dict, flow: dict, inputs):
    try:
        # 本段执行开始的确定信号：轮询方据此区分「过期的 waiting_human」与「重新挂起」
        await store.update_run(run["run_id"], status="running")
        await runner.execute(run, flow, inputs, agent_factory=_agent_factory,
                             checkpointer=await _get_checkpointer(),
                             on_event=lambda e: _publish(run["run_id"], e))
    except Exception as exc:  # noqa: BLE001
        await store.update_run(run["run_id"], status="failed", error=str(exc))
    finally:
        _INFLIGHT.discard(run["run_id"])
        for q in _EVENT_QUEUES.get(run["run_id"], []):
            await q.put(None)  # 通知订阅者：本段执行结束


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------- 流程 CRUD（管理员） ----------

@router.get("/flows")
async def list_flows(_: dict = Depends(require_admin)):
    return {"flows": await store.list_flows()}


@router.post("/flows")
async def create_flow(body: FlowBody, _: dict = Depends(require_admin)):
    try:
        dsl.validate(body.definition)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"flow": await store.create_flow(body.name, body.definition)}


@router.get("/flows/{flow_id}")
async def get_flow(flow_id: str, _: dict = Depends(require_admin)):
    flow = await store.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="流程不存在")
    return {"flow": flow}


@router.put("/flows/{flow_id}")
async def update_flow(flow_id: str, body: FlowUpdateBody,
                      _: dict = Depends(require_admin)):
    if body.definition is not None:
        try:
            dsl.validate(body.definition)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    flow = await store.update_flow(flow_id, name=body.name, definition=body.definition)
    if not flow:
        raise HTTPException(status_code=404, detail="流程不存在")
    return {"flow": flow}


@router.delete("/flows/{flow_id}")
async def delete_flow(flow_id: str, _: dict = Depends(require_admin)):
    if not await store.delete_flow(flow_id):
        raise HTTPException(status_code=404, detail="流程不存在")
    return {"status": "deleted", "flow_id": flow_id}


# ---------- 发起与实例（登录用户） ----------

@router.post("/flows/{flow_id}/runs")
async def start_flow_run(flow_id: str, body: RunBody,
                         user: dict = Depends(get_current_user)):
    flow = await store.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="流程不存在")
    try:
        run, flow = await runner.prepare_start(flow_id, body.input)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _INFLIGHT.add(run["run_id"])
    _spawn(_execute_detached(run, flow, {"input": run["input"], "outputs": {},
                                         "edge_counts": {}}))
    return {"run": run}


@router.get("/flow-runs")
async def list_flow_runs(flow_id: str | None = None,
                         user: dict = Depends(get_current_user)):
    return {"runs": await store.list_runs(flow_id)}


@router.get("/flow-runs/{run_id}")
async def get_flow_run(run_id: str, user: dict = Depends(get_current_user)):
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="实例不存在")
    flow = await store.get_flow(run["flow_id"])
    return {"run": run,
            "pending": runner.pending_request(flow, run) if flow else None}


@router.post("/flow-runs/{run_id}/resume")
async def resume_flow_run(run_id: str, body: dict,
                          user: dict = Depends(get_current_user)):
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="实例不存在")
    if run_id in _INFLIGHT:
        raise HTTPException(status_code=400, detail="实例正在执行中，请稍后再试")
    try:
        run, flow = await runner.prepare_resume(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _INFLIGHT.add(run_id)
    _spawn(_execute_detached(run, flow, Command(resume=body)))
    return {"run": run}


@router.post("/flow-runs/{run_id}/cancel")
async def cancel_flow_run(run_id: str, user: dict = Depends(get_current_user)):
    run = await runner.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="实例不存在")
    await _publish(run_id, {"event": "flow_status", "status": run["status"],
                            "error": None})
    return {"run": run}


@router.get("/flow-runs/{run_id}/stream")
async def stream_flow_run(run_id: str, user: dict = Depends(get_current_user)):
    """SSE 进度流：快照 → 回放历史 flow_step → 跟随订阅，flow_status/done 收尾。"""

    async def gen():
        run = await store.get_run(run_id)
        if not run:
            yield _sse("error", {"message": "实例不存在"})
            return
        yield _sse("flow_status", {"status": run["status"],
                                   "current_node": run["current_node"],
                                   "error": run["error"]})
        for ev in list(_EVENT_LOGS.get(run_id, [])):  # 回放历史节点事件
            yield _sse(ev["event"], ev)
        if run["status"] in TERMINAL_STATUSES or run["status"] == "waiting_human":
            yield _sse("done", {})
            return
        q: asyncio.Queue = asyncio.Queue()
        _EVENT_QUEUES.setdefault(run_id, []).append(q)
        try:
            while True:
                ev = await q.get()
                if ev is None:  # 执行段结束（无 flow_status 时的兜底）
                    break
                yield _sse(ev["event"], ev)
                if ev.get("event") == "flow_status":
                    break
        finally:
            try:
                _EVENT_QUEUES[run_id].remove(q)
            except (KeyError, ValueError):
                pass
        yield _sse("done", {})

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
