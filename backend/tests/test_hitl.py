"""HITL 回归测试：集中配置合法性 + 中断事件（on_interrupt）解析。

这些测试不依赖外部 LLM：验证「哪些工具需要人工介入」的配置格式正确，
以及后端从 on_interrupt 事件中提取 HITLRequest 的逻辑正确——这正是
前端渲染确认/回复面板的数据来源。
"""

import os
import sys

# 让 backend 进入 sys.path，便于 import main / agent 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.deep_agent import INTERRUPT_TOOLS  # noqa: E402
from main import _extract_interrupt_requests  # noqa: E402

_VALID_DECISIONS = {"approve", "reject", "respond", "edit"}


def test_interrupt_tools_config_valid():
    """INTERRUPT_TOOLS 中每个工具的 allowed_decisions 必须是合法的决策类型。"""
    assert INTERRUPT_TOOLS, "INTERRUPT_TOOLS 不应为空（至少应声明需要人工介入的工具）"
    for tool, cfg in INTERRUPT_TOOLS.items():
        assert isinstance(tool, str) and tool, f"工具名非法: {tool!r}"
        assert isinstance(cfg, dict), f"{tool} 的配置应为 dict"
        decisions = cfg.get("allowed_decisions")
        assert isinstance(decisions, list) and decisions, (
            f"{tool} 的 allowed_decisions 必须是非空列表"
        )
        assert set(decisions) <= _VALID_DECISIONS, (
            f"{tool} 含非法决策类型: {set(decisions) - _VALID_DECISIONS}"
        )


def test_extract_interrupt_requests_from_dataclass():
    """从 on_interrupt 事件 data（dataclass 形态）正确提取 HITLRequest。"""

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeData:
        def __init__(self, interrupts):
            self.interrupts = interrupts

    hitl = {
        "action_requests": [
            {"name": "create_work_order", "args": {"title": "x"}, "description": "d"}
        ],
        "review_configs": [
            {"action_name": "create_work_order", "allowed_decisions": ["approve", "reject"]}
        ],
    }
    data = FakeData([FakeInterrupt(hitl)])
    reqs = _extract_interrupt_requests(data)
    assert len(reqs) == 1
    assert reqs[0]["action_requests"][0]["name"] == "create_work_order"
    assert reqs[0]["review_configs"][0]["allowed_decisions"] == ["approve", "reject"]


def test_extract_interrupt_requests_dict_form():
    """兼容 data 以普通 dict 暴露 interrupts 的情况。"""
    hitl = {
        "action_requests": [{"name": "ask_human", "args": {"question": "选A还是B？"}}],
        "review_configs": [{"action_name": "ask_human", "allowed_decisions": ["respond"]}],
    }
    data = {"interrupts": [{"value": hitl}]}
    reqs = _extract_interrupt_requests(data)
    assert reqs[0]["action_requests"][0]["args"]["question"] == "选A还是B？"


def test_extract_interrupt_requests_empty():
    """无中断或无法识别的 data 应安全返回空列表，不抛异常。"""
    assert _extract_interrupt_requests(None) == []
    assert _extract_interrupt_requests(object()) == []
    assert _extract_interrupt_requests({"interrupts": []}) == []
