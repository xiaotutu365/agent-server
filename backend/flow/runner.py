"""flow runner：按 definition 动态构建 StateGraph 并执行（SPEC-flow-config 3.3）。

- thread_id = flow:{run_id}，checkpointer 由调用方注入（生产用 AsyncSqliteSaver，
  与聊天会话同库 → 人审暂停可跨进程恢复；测试用 InMemorySaver）
- agent 工厂依赖注入（api 层接 main.get_agent_for），避免 runner 循环 import
- llm 节点复用缓存构建的 deep agent；tool 节点走 REGISTRY 真工具（to_thread 不阻塞事件循环）
- human 节点 interrupt(payload) 暂停（status=waiting_human），resume 走 Command(resume=...)
- 循环守卫：同一 human 决策边通过次数超过 limits.max_revisions → failed
"""

import asyncio
import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from flow import store
from flow.dsl import validate

DEFAULT_MAX_REVISIONS = 5
_INTERP = re.compile(r"\$\{([^}]+)\}")


class FlowState(TypedDict):
    input: dict                                   # 用户输入
    outputs: dict                                 # output_key → 内容
    edge_counts: dict                             # "node:decision" → 通过次数（守卫）


class FlowGuardError(RuntimeError):
    """max_revisions 超限（防死循环）。"""


async def start_run(flow_id: str, run_input: dict, *, agent_factory, checkpointer,
                    on_event=None) -> dict:
    """创建实例并执行到完成/人审暂停，返回最新 run 行。"""
    run, flow = await prepare_start(flow_id, run_input)
    return await execute(run, flow, {"input": run_input, "outputs": {}, "edge_counts": {}},
                         agent_factory=agent_factory, checkpointer=checkpointer,
                         on_event=on_event)


async def resume_run(run_id: str, resume, *, agent_factory, checkpointer,
                     on_event=None) -> dict:
    """人审决策后恢复（与聊天 HITL 同协议：Command(resume=...)）。"""
    run, flow = await prepare_resume(run_id)
    return await execute(run, flow, Command(resume=resume), agent_factory=agent_factory,
                         checkpointer=checkpointer, on_event=on_event)


async def prepare_start(flow_id: str, run_input: dict) -> tuple[dict, dict]:
    """发起前置：校验流程并建 run 行（不执行）。返回 (run, flow) 供脱离执行。"""
    flow = await store.get_flow(flow_id)
    if not flow:
        raise ValueError(f"流程 {flow_id} 不存在")
    validate(flow["definition"])
    run = await store.create_run(flow_id, run_input)
    return run, flow


async def prepare_resume(run_id: str) -> tuple[dict, dict]:
    """恢复前置：校验状态（仅 waiting_human 可恢复）。返回 (run, flow)。"""
    run = await store.get_run(run_id)
    if not run:
        raise ValueError(f"实例 {run_id} 不存在")
    if run["status"] != "waiting_human":
        raise ValueError(f"实例当前状态为 {run['status']}，不在等待人审")
    flow = await store.get_flow(run["flow_id"])
    if not flow:
        raise ValueError(f"流程 {run['flow_id']} 不存在")
    return run, flow


async def execute(run: dict, flow: dict, inputs, *, agent_factory, checkpointer,
                  on_event=None) -> dict:
    """执行图到完成/人审暂停/失败，返回最新 run 行（供后台任务脱离调用）。"""
    return await _execute(run, flow, inputs, agent_factory, checkpointer, on_event)


async def cancel_run(run_id: str) -> dict | None:
    """取消运行（仅 running/waiting_human 可取消；图执行侧由调用方中止）。"""
    run = await store.get_run(run_id)
    if not run or run["status"] not in ("running", "waiting_human"):
        return run
    return await store.update_run(run_id, status="cancelled")


def pending_request(flow: dict, run: dict) -> dict | None:
    """waiting_human 时的待审批内容（interrupt 载荷为节点静态定义，可从 definition 推导）。"""
    if run["status"] != "waiting_human" or not run["current_node"]:
        return None
    for node in flow["definition"]["nodes"]:
        if node["id"] == run["current_node"]:
            return {"node": node["id"], "prompt": node.get("prompt", ""),
                    "output_key": node["output_key"]}
    return None


# ---------- 内部执行 ----------

async def _maybe_await(fn, event: dict):
    """事件回调兼容同步函数与异步函数。"""
    out = fn(event)
    if asyncio.iscoroutine(out):
        await out


async def _execute(run: dict, flow: dict, inputs, agent_factory, checkpointer,
                   on_event) -> dict:
    graph = _build_graph(flow["definition"], run["run_id"], agent_factory, on_event,
                         checkpointer)
    config = {
        "configurable": {"thread_id": f"flow:{run['run_id']}"},
        "recursion_limit": _recursion_limit(flow["definition"]),
    }

    async def emit(event: dict):
        if on_event:
            await _maybe_await(on_event, event)

    try:
        result = await graph.ainvoke(inputs, config=config)
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, asyncio.CancelledError):
            raise
        await emit({"event": "flow_status", "status": "failed", "error": str(exc)})
        return await store.update_run(run["run_id"], status="failed", error=str(exc))
    if "__interrupt__" in result:  # 人审暂停：图挂起，等待 resume
        await emit({"event": "flow_status", "status": "waiting_human", "error": None})
        return await store.get_run(run["run_id"])
    state = await graph.aget_state(config)
    outputs = (state.values or {}).get("outputs", {}) if state else {}
    await emit({"event": "flow_status", "status": "done", "error": None})
    return await store.update_run(run["run_id"], status="done", outputs=outputs)


def _recursion_limit(definition: dict) -> int:
    max_rev = (definition.get("limits") or {}).get("max_revisions", DEFAULT_MAX_REVISIONS)
    return len(definition["nodes"]) * (max_rev + 2) * 2 + 50


def _build_graph(definition: dict, run_id: str, agent_factory, on_event,
                 checkpointer) -> StateGraph:
    nodes = {n["id"]: n for n in definition["nodes"]}
    out_edges: dict[str, list] = {}
    for e in definition["edges"]:
        out_edges.setdefault(e["from"], []).append(e)

    async def emit_step(node: dict, status: str):
        if on_event:
            await _maybe_await(
                on_event, {"event": "flow_step", "node": node["id"], "status": status})

    graph = StateGraph(FlowState)

    def make_node(node: dict):
        ntype = node["type"]
        if ntype == "llm":
            return _llm_node(node, run_id, agent_factory, emit_step)
        if ntype == "tool":
            return _tool_node(node, run_id, emit_step)
        return _human_node(node, run_id, definition, emit_step)

    for nid, node in nodes.items():
        graph.add_node(nid, make_node(node))
        router = _make_router(node, out_edges.get(nid, []))
        graph.add_conditional_edges(nid, router)
    graph.add_edge(START, definition["entry"])
    return graph.compile(checkpointer=checkpointer)


def _interpolate(text: str, state: dict) -> str:
    """${output_key} → 上游产出；${input} → 用户输入 JSON；${input.x} → 输入字段。"""
    def sub(m):
        key = m.group(1).strip()
        if key == "input":
            return json.dumps(state["input"], ensure_ascii=False)
        if key.startswith("input."):
            val = state["input"]
            for part in key[len("input."):].split("."):
                val = val.get(part) if isinstance(val, dict) else None
            return "" if val is None else str(val)
        if key in state["outputs"]:
            return str(state["outputs"][key])
        raise ValueError(f"插值引用不存在的输出 ${{{key}}}")

    return _INTERP.sub(sub, text)


def _last_ai_text(result) -> str:
    """从 agent.ainvoke 结果取最后一条 AI 消息文本（兼容 message 对象与 dict）。"""
    msgs = (result or {}).get("messages") or []
    for msg in reversed(msgs):
        role = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else "")
        if role == "ai" or role == "assistant":
            content = getattr(msg, "content", None)
            if content is None and isinstance(msg, dict):
                content = msg.get("content")
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")
            if content:
                return content
    raise ValueError("llm 节点未产出任何 AI 回复")


def _llm_node(node: dict, run_id: str, agent_factory, emit_step):
    async def fn(state: FlowState):
        nid = node["id"]
        await store.update_run(run_id, status="running", current_node=nid)
        await emit_step(node, "running")
        text = _interpolate(node.get("input") or json.dumps(state["input"],
                                                            ensure_ascii=False), state)
        agent = await agent_factory(node)
        config = {
            "configurable": {"thread_id": f"flow:{run_id}:{nid}"},
            "recursion_limit": 100,
        }
        result = await agent.ainvoke({"messages": [{"role": "user", "content": text}]},
                                     config=config)
        content = _last_ai_text(result)
        outputs = {**state["outputs"], node["output_key"]: content}
        await store.update_run(run_id, outputs=outputs)  # 增量落库，暂停/运行中均可见
        await emit_step(node, "done")
        return {"outputs": outputs}

    return fn


def _tool_node(node: dict, run_id: str, emit_step):
    async def fn(state: FlowState):
        nid = node["id"]
        await store.update_run(run_id, status="running", current_node=nid)
        await emit_step(node, "running")
        args = {
            k: _interpolate(v, state) if isinstance(v, str) else v
            for k, v in (node.get("args") or {}).items()
        }
        from agent.tool_registry import get_tool

        tool = get_tool(node["tool"])
        result = await asyncio.to_thread(tool.invoke, args)  # 红线：同步工具不阻塞事件循环
        outputs = {**state["outputs"], node["output_key"]: str(result)}
        await store.update_run(run_id, outputs=outputs)
        await emit_step(node, "done")
        return {"outputs": outputs}

    return fn


def _human_node(node: dict, run_id: str, definition: dict, emit_step):
    max_rev = (definition.get("limits") or {}).get("max_revisions", DEFAULT_MAX_REVISIONS)

    async def fn(state: FlowState):
        nid = node["id"]
        await store.update_run(run_id, status="waiting_human", current_node=nid,
                               outputs=state["outputs"])  # 审批人需看到已产出的内容
        await emit_step(node, "running")
        resume = interrupt({"node": nid, "prompt": node.get("prompt", ""),
                            "output_key": node["output_key"]})
        await store.update_run(run_id, status="running")  # 已恢复，继续往下走
        value = resume.get("decision") if isinstance(resume, dict) else str(resume)
        key = f"{nid}:{value}"
        counts = {**state.get("edge_counts", {})}
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > max_rev:
            raise FlowGuardError(
                f"max_revisions({max_rev}) 超限：{key} 已通过 {counts[key]} 次，自动终止")
        await emit_step(node, "done")
        return {"outputs": {**state["outputs"], node["output_key"]: resume},
                "edge_counts": counts}

    return fn


def _make_router(node: dict, edges: list):
    """条件路由：when 边按人审决策值匹配；无匹配走无条件边；都没有则结束。"""
    when_edges = [e for e in edges if e.get("when")]
    defaults = [e for e in edges if not e.get("when")]
    output_key = node["output_key"]

    def router(state: FlowState):
        if when_edges:
            raw = state["outputs"].get(output_key)
            value = raw.get("decision") if isinstance(raw, dict) else raw
            for e in when_edges:
                if e["when"] == value:
                    return e["to"]
        if defaults:
            return defaults[0]["to"]
        return END

    return router
