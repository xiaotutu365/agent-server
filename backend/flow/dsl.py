"""流程 DSL 校验（SPEC-flow-config 3.2）。

definition 结构（JSON）：
{
  "entry": "<node_id>",                     # 显式入口（修订回环下首节点可有入边）
  "nodes": [ {"id", "type": llm|tool|human, "output_key", ...} ],
  "edges": [ {"from", "to", "when"?: approved|rejected} ],
  "limits": {"max_revisions": int}          # 可选
}
- llm 节点：agent.system_prompt 必填；kb_ids/tools/model_id 可选（节点级覆盖）
- tool 节点：tool（REGISTRY 内名字）+ args（支持 ${output_key} 插值，运行期解析）
- human 节点：prompt 必填（展示给审批人）；timeout_hours 可选（首期仅记录）

校验失败 raise ValueError，信息带字段路径（如 nodes[0].type），API 层转 400。
"""

ALLOWED_NODE_TYPES = {"llm", "tool", "human"}
ALLOWED_WHEN = {"approved", "rejected"}


def validate(definition, known_tools: set | None = None) -> dict:
    """校验并原样返回 definition；非法抛 ValueError。known_tools 缺省对照真实 REGISTRY。"""
    if not isinstance(definition, dict) or not isinstance(definition.get("nodes"), list) \
            or not definition["nodes"] or not isinstance(definition.get("edges"), list):
        raise ValueError("definition: 须为含非空 nodes 列表与 edges 列表的对象")

    ids = set()
    for i, node in enumerate(definition["nodes"]):
        _validate_node(i, node, ids, known_tools)

    entry = definition.get("entry")
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError("definition.entry: 必填（显式指定入口节点，修订回环下首节点可有入边）")
    if entry not in ids:
        raise ValueError(f"definition.entry: 引用不存在的节点 {entry!r}")

    for i, edge in enumerate(definition["edges"]):
        if not isinstance(edge, dict) or not edge.get("from") or not edge.get("to"):
            raise ValueError(f"edges[{i}]: from/to 必填且非空")
        if edge["from"] not in ids:
            raise ValueError(f"edges[{i}].from: 引用不存在的节点 {edge['from']!r}")
        if edge["to"] not in ids:
            raise ValueError(f"edges[{i}].to: 引用不存在的节点 {edge['to']!r}")
        when = edge.get("when")
        if when is not None and when not in ALLOWED_WHEN:
            raise ValueError(
                f"edges[{i}].when: 非法值 {when!r}（首期仅支持 {'/'.join(sorted(ALLOWED_WHEN))}）")

    limits = definition.get("limits")
    if limits is not None:
        mr = (limits or {}).get("max_revisions")
        if not isinstance(mr, int) or isinstance(mr, bool) or mr < 1:
            raise ValueError("limits.max_revisions: 须为 ≥1 的整数")
    return definition


def _validate_node(i: int, node, ids: set, known_tools: set | None):
    if not isinstance(node, dict):
        raise ValueError(f"nodes[{i}]: 须为对象")
    nid = node.get("id")
    if not isinstance(nid, str) or not nid.strip():
        raise ValueError(f"nodes[{i}].id: 必填且非空")
    if nid in ids:
        raise ValueError(f"nodes[{i}].id: 节点 id {nid!r} 重复")
    ids.add(nid)

    ntype = node.get("type")
    if ntype not in ALLOWED_NODE_TYPES:
        raise ValueError(
            f"nodes[{i}].type: 未知节点类型 {ntype!r}（支持 {'/'.join(sorted(ALLOWED_NODE_TYPES))}）")

    if not isinstance(node.get("output_key"), str) or not node["output_key"].strip():
        raise ValueError(f"nodes[{i}].output_key: 必填且非空")

    if ntype == "llm":
        agent = node.get("agent")
        sp = (agent or {}).get("system_prompt")
        if not isinstance(sp, str) or not sp.strip():
            raise ValueError(f"nodes[{i}].agent.system_prompt: llm 节点必填")
    elif ntype == "tool":
        tool_name = node.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError(f"nodes[{i}].tool: tool 节点必填")
        tools = known_tools if known_tools is not None else _registry_tool_names()
        if tool_name not in tools:
            raise ValueError(f"nodes[{i}].tool: 未注册的工具 {tool_name!r}")
    else:  # human
        if not isinstance(node.get("prompt"), str) or not node["prompt"].strip():
            raise ValueError(f"nodes[{i}].prompt: human 节点必填（展示给审批人）")


def _registry_tool_names() -> set:
    """懒加载真实工具注册表，避免 dsl 模块被轻量引用时拖入全量工具链。"""
    from agent.tool_registry import ALL_TOOL_NAMES

    return set(ALL_TOOL_NAMES)
