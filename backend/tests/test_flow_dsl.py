"""DSL 校验器测试（SPEC-flow-config 3.2）：合法定义通过，非法定义报带字段名的错误。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from flow.dsl import validate  # noqa: E402

TOOLS = {"write_file", "web_search"}


def valid_definition() -> dict:
    return {
        "entry": "generate",
        "nodes": [
            {"id": "generate", "type": "llm", "output_key": "draft",
             "agent": {"system_prompt": "你是文案作者"}},
            {"id": "review", "type": "human", "output_key": "decision", "prompt": "请审批初稿"},
            {"id": "write", "type": "tool", "output_key": "result",
             "tool": "web_search", "args": {"query": "${draft}"}},
        ],
        "edges": [
            {"from": "generate", "to": "review"},
            {"from": "review", "to": "write", "when": "approved"},
            {"from": "review", "to": "generate", "when": "rejected"},
        ],
        "limits": {"max_revisions": 3},
    }


def test_valid_definition_passes():
    assert validate(valid_definition(), known_tools=TOOLS) == valid_definition()


def test_not_a_dict_or_empty_nodes():
    for bad in (None, [], {}, {"nodes": []}, {"nodes": [], "edges": []}):
        with pytest.raises(ValueError, match="nodes"):
            validate(bad, known_tools=TOOLS)


def test_unknown_node_type():
    d = valid_definition()
    d["nodes"][0]["type"] = "magic"
    with pytest.raises(ValueError, match=r"nodes\[0\]\.type"):
        validate(d, known_tools=TOOLS)


def test_node_id_missing_or_duplicate():
    d = valid_definition()
    del d["nodes"][1]["id"]
    with pytest.raises(ValueError, match=r"nodes\[1\]\.id"):
        validate(d, known_tools=TOOLS)

    d2 = valid_definition()
    d2["nodes"][1]["id"] = "generate"
    with pytest.raises(ValueError, match="重复"):
        validate(d2, known_tools=TOOLS)


def test_output_key_required():
    d = valid_definition()
    del d["nodes"][0]["output_key"]
    with pytest.raises(ValueError, match=r"nodes\[0\]\.output_key"):
        validate(d, known_tools=TOOLS)


def test_llm_node_requires_system_prompt():
    d = valid_definition()
    del d["nodes"][0]["agent"]["system_prompt"]
    with pytest.raises(ValueError, match=r"nodes\[0\]\.agent\.system_prompt"):
        validate(d, known_tools=TOOLS)


def test_tool_node_requires_known_tool():
    d = valid_definition()
    del d["nodes"][2]["tool"]
    with pytest.raises(ValueError, match=r"nodes\[2\]\.tool"):
        validate(d, known_tools=TOOLS)

    d["nodes"][2]["tool"] = "no_such_tool"
    with pytest.raises(ValueError, match="no_such_tool"):
        validate(d, known_tools=TOOLS)


def test_human_node_requires_prompt():
    d = valid_definition()
    del d["nodes"][1]["prompt"]
    with pytest.raises(ValueError, match=r"nodes\[1\]\.prompt"):
        validate(d, known_tools=TOOLS)


def test_edge_references_unknown_node():
    d = valid_definition()
    d["edges"][0]["to"] = "ghost"
    with pytest.raises(ValueError, match=r"edges\[0\]\.to"):
        validate(d, known_tools=TOOLS)


def test_edge_when_invalid_value():
    d = valid_definition()
    d["edges"][1]["when"] = "maybe"
    with pytest.raises(ValueError, match=r"edges\[1\]\.when"):
        validate(d, known_tools=TOOLS)


def test_entry_required_and_must_exist():
    # 缺 entry / 引用不存在节点
    d = valid_definition()
    del d["entry"]
    with pytest.raises(ValueError, match=r"definition\.entry"):
        validate(d, known_tools=TOOLS)

    d2 = valid_definition()
    d2["entry"] = "ghost"
    with pytest.raises(ValueError, match=r"definition\.entry"):
        validate(d2, known_tools=TOOLS)

    # 修订回环（rejected → generate）+ 显式 entry 是合法形态
    d3 = valid_definition()
    assert validate(d3, known_tools=TOOLS) == d3


def test_max_revisions_validation():
    d = valid_definition()
    d["limits"]["max_revisions"] = 0
    with pytest.raises(ValueError, match="max_revisions"):
        validate(d, known_tools=TOOLS)

    d2 = valid_definition()
    del d2["limits"]  # limits 整体可省略
    assert validate(d2, known_tools=TOOLS) == d2


def test_default_validates_against_real_registry():
    """不传 known_tools 时对照真实 REGISTRY（懒加载，冒烟一次）。"""
    from agent.tool_registry import ALL_TOOL_NAMES

    d = valid_definition()
    assert validate(d) == d
