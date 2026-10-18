"""flow runner 测试：动态 StateGraph 执行。

T3a：线性执行 + ${} 插值 + 状态落库；T3b：人审 interrupt/resume、条件边、max_revisions 守卫。
checkpointer 用 InMemorySaver；跨进程持久化恢复由 T5 curl 冒烟覆盖。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from flow import runner, store  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    yield


@pytest.fixture()
def inited(tmp_db):
    asyncio.run(store.init_flow_tables())
    yield


class FakeAgent:
    """llm 节点的假 agent：记录收到的消息，回固定内容。"""

    def __init__(self, reply="初稿内容"):
        self.reply = reply
        self.calls = []

    async def ainvoke(self, inputs, config=None):
        self.calls.append(inputs)
        return {"messages": list(inputs["messages"]) + [
            {"role": "assistant", "content": self.reply}]}


def make_factory(agent):
    async def factory(node):
        return agent

    return factory


def _start(flow_id, run_input, agent, checkpointer=None, **kw):
    return asyncio.run(runner.start_run(
        flow_id, run_input, agent_factory=make_factory(agent),
        checkpointer=checkpointer or InMemorySaver(), **kw))


# ---------- T3a：线性 + 插值 ----------

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


def test_linear_llm_then_tool(inited):
    """llm → tool 顺序执行，outputs 逐节点累积并落库。"""
    f = asyncio.run(store.create_flow("线性", linear_definition()))
    agent = FakeAgent()
    run = _start(f["flow_id"], {"topic": "Q3 计划"}, agent)

    assert run["status"] == "done"
    assert run["outputs"]["draft"] == "初稿内容"
    assert run["outputs"]["result"] == "1+1 = 2"  # REGISTRY 真工具 calculator
    assert run["current_node"] == "calc"
    assert run["error"] is None
    # llm 收到 ${input.topic} 插值后的输入
    assert agent.calls[0]["messages"][-1]["content"] == "主题：Q3 计划"
    # 落库一致
    assert asyncio.run(store.get_run(run["run_id"]))["outputs"] == run["outputs"]


def test_tool_args_interpolate_previous_output(inited):
    """${output_key} 把上游产出插进工具入参。"""
    d = linear_definition()
    d["nodes"][0]["input"] = "算式：${input.expr}"
    d["nodes"][1]["args"] = {"expression": "${draft}"}
    f = asyncio.run(store.create_flow("插值", d))
    run = _start(f["flow_id"], {"expr": "2+3"}, FakeAgent(reply="2+3"))
    assert run["outputs"]["result"] == "2+3 = 5"


def test_llm_node_without_input_template_gets_run_input(inited):
    """节点无 input 模板时，把用户输入 JSON 作为消息内容。"""
    d = linear_definition()
    del d["nodes"][0]["input"]
    f = asyncio.run(store.create_flow("缺省输入", d))
    agent = FakeAgent()
    _start(f["flow_id"], {"topic": "Q3"}, agent)
    assert '"topic"' in agent.calls[0]["messages"][-1]["content"]


def test_node_progress_recorded_via_events(inited):
    """on_event 逐节点上报 flow_step（running→done），run 级 flow_status 收尾。"""
    f = asyncio.run(store.create_flow("事件", linear_definition()))
    events = []
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent(),
                 on_event=events.append)
    assert run["status"] == "done"
    steps = [e for e in events if e["event"] == "flow_step"]
    assert [e["node"] for e in steps] == ["generate", "generate", "calc", "calc"]
    assert [e["status"] for e in steps] == ["running", "done", "running", "done"]
    assert events[-1] == {"event": "flow_status", "status": "done", "error": None}


# ---------- T3b：人审 / 条件边 / 守卫 ----------

def review_definition(max_revisions: int | None = None) -> dict:
    d = {
        "entry": "generate",
        "nodes": [
            {"id": "generate", "type": "llm", "output_key": "draft",
             "agent": {"system_prompt": "作者"}, "input": "主题：${input.topic}"},
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
    if max_revisions is not None:
        d["limits"] = {"max_revisions": max_revisions}
    return d


def test_human_interrupt_pauses_then_resume_approves(inited):
    """human 节点 interrupt 暂停（waiting_human）→ Command(resume) 恢复跑完。"""
    f = asyncio.run(store.create_flow("审批", review_definition()))
    cp = InMemorySaver()
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent(), checkpointer=cp)
    assert run["status"] == "waiting_human"
    assert run["current_node"] == "review"

    # 待审批内容从 definition 推导（详情页用）
    assert runner.pending_request(f, run) == {
        "node": "review", "prompt": "请审批初稿", "output_key": "decision"}

    run2 = asyncio.run(runner.resume_run(
        run["run_id"], {"decision": "approved", "comment": "ok"},
        agent_factory=make_factory(FakeAgent()), checkpointer=cp))
    assert run2["status"] == "done"
    assert run2["outputs"]["decision"] == {"decision": "approved", "comment": "ok"}
    assert run2["outputs"]["result"] == "1+1 = 2"
    assert runner.pending_request(f, run2) is None


def test_rejected_loops_back_to_human(inited):
    """rejected 走条件边回到 llm，再次人审；approved 后跑完。"""
    f = asyncio.run(store.create_flow("修订", review_definition()))
    cp = InMemorySaver()
    agent = FakeAgent()
    run = _start(f["flow_id"], {"topic": "t"}, agent, checkpointer=cp)

    run2 = asyncio.run(runner.resume_run(
        run["run_id"], {"decision": "rejected", "comment": "重写"},
        agent_factory=make_factory(agent), checkpointer=cp))
    assert run2["status"] == "waiting_human"  # 回到人审点
    assert run2["current_node"] == "review"
    assert len(agent.calls) == 2  # llm 被重新执行
    assert "result" not in run2["outputs"]  # approved 分支未走

    run3 = asyncio.run(runner.resume_run(
        run2["run_id"], {"decision": "approved"},
        agent_factory=make_factory(agent), checkpointer=cp))
    assert run3["status"] == "done"
    assert run3["outputs"]["result"] == "1+1 = 2"


def test_max_revisions_guard_fails_run(inited):
    """同一决策边通过次数超过 max_revisions → failed 且 error 说明原因。"""
    f = asyncio.run(store.create_flow("守卫", review_definition(max_revisions=2)))
    cp = InMemorySaver()
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent(), checkpointer=cp)

    for i in range(2):  # 拒绝 2 次（= 上限，仍可继续）
        run = asyncio.run(runner.resume_run(
            run["run_id"], {"decision": "rejected"},
            agent_factory=make_factory(FakeAgent()), checkpointer=cp))
        assert run["status"] == "waiting_human"

    run = asyncio.run(runner.resume_run(
        run["run_id"], {"decision": "rejected"},
        agent_factory=make_factory(FakeAgent()), checkpointer=cp))
    assert run["status"] == "failed"
    assert "max_revisions(2)" in run["error"]


def test_resume_non_waiting_run_rejected(inited):
    """非 waiting_human 状态的实例不允许 resume。"""
    f = asyncio.run(store.create_flow("线性", linear_definition()))
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent())
    assert run["status"] == "done"
    with pytest.raises(ValueError, match="不在等待人审"):
        asyncio.run(runner.resume_run(
            run["run_id"], {"decision": "approved"},
            agent_factory=make_factory(FakeAgent()), checkpointer=InMemorySaver()))


def test_outputs_visible_while_waiting_human(inited):
    """人审暂停时 run 行已含上游产出（审批人需看到初稿）。"""
    f = asyncio.run(store.create_flow("审批", review_definition()))
    cp = InMemorySaver()
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent(), checkpointer=cp)
    assert run["status"] == "waiting_human"
    assert run["outputs"]["draft"] == "初稿内容"


def test_cancel_run(inited):
    """waiting_human 实例可取消；终态实例取消不生效。"""
    f = asyncio.run(store.create_flow("审批", review_definition()))
    cp = InMemorySaver()
    run = _start(f["flow_id"], {"topic": "t"}, FakeAgent(), checkpointer=cp)
    assert run["status"] == "waiting_human"
    cancelled = asyncio.run(runner.cancel_run(run["run_id"]))
    assert cancelled["status"] == "cancelled"
    # 已终态实例：取消不改变状态
    assert asyncio.run(runner.cancel_run(run["run_id"]))["status"] == "cancelled"
