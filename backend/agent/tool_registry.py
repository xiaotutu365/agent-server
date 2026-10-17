"""工具注册表：集中登记所有可分配给 agent 的工具。

后台配置页据此列出「按分组组织的工具目录」，并在保存配置后由
deep_agent.build_agent 通过 resolve_tools 计算实际加载的工具子集。
新增工具只需在对应模块的 TOOLS 列表里加 @tool 函数，这里会自动收录。
"""

from agent.human_tools import HUMAN_TOOLS
from agent.memory_tools import MEMORY_TOOLS
from kb.tools import KB_TOOLS, make_kb_tools
from tools.crm_tools import CRM_TOOLS
from tools.custom_tools import CUSTOM_TOOLS
from tools.search_tools import SEARCH_TOOLS

# 分组：决定后台展示分组，以及记忆/知识库「总开关」的作用域
GROUPS = [
    ("search", "联网搜索", SEARCH_TOOLS),
    ("compute", "计算", CUSTOM_TOOLS),
    ("crm", "CRM 业务", CRM_TOOLS),
    ("memory", "长期记忆", MEMORY_TOOLS),
    ("kb", "知识库", KB_TOOLS),
    ("hitl", "人机交互", HUMAN_TOOLS),
]

# name -> {func, group, group_label, description}
REGISTRY = {}
for _gkey, _glabel, _tools in GROUPS:
    for _t in _tools:
        REGISTRY[_t.name] = {
            "func": _t,
            "group": _gkey,
            "group_label": _glabel,
            "description": (_t.description or "").strip().split("\n")[0],
        }

ALL_TOOL_NAMES = list(REGISTRY.keys())


def _extract_schema(func):
    """从 langchain @tool 抽取参数定义：属性名 -> 类型 / 必填 / 默认值 / 描述。"""
    props, required, raw = {}, [], None
    try:
        schema_model = getattr(func, "args_schema", None)
        if schema_model is not None:
            raw = schema_model.model_json_schema()
            props = raw.get("properties", {})
            required = raw.get("required", [])
        elif getattr(func, "args", None):
            props = func.args
    except Exception:  # noqa: BLE001
        props, required, raw = {}, [], None

    out = []
    for name, spec in props.items():
        spec = spec or {}
        ptype = spec.get("type")
        if not ptype and spec.get("anyOf"):
            ptype = spec["anyOf"][0].get("type", "any")
        out.append({
            "name": name,
            "type": ptype or "any",
            "required": name in required,
            "default": None if name in required else spec.get("default"),
            "description": spec.get("description", ""),
        })
    return out, raw


def get_tool_detail(name: str):
    """单个工具的完整详情：分组、提示词（完整描述）、参数 schema。"""
    meta = REGISTRY.get(name)
    if not meta:
        return None
    params, raw = _extract_schema(meta["func"])
    return {
        "name": name,
        "group": meta["group"],
        "group_label": meta["group_label"],
        "prompt": (meta["func"].description or "").strip(),
        "params": params,
        "schema": raw,
    }


def get_tool(name: str):
    return REGISTRY[name]["func"]


def list_tools():
    """返回按分组组织的工具目录，供后台配置页展示。"""
    out = []
    for gkey, glabel, _ in GROUPS:
        items = [
            {"name": n, "description": m["description"]}
            for n, m in REGISTRY.items()
            if m["group"] == gkey
        ]
        out.append({"key": gkey, "label": glabel, "tools": items})
    return out


def resolve_tools(config: dict) -> list:
    """根据配置筛选实际加载的工具函数列表。

    - tools_enabled：逐项开关（工具名列表）
    - memory_enabled / kb_enabled：记忆 / 知识库「总开关」，关闭时强制排除对应组
    - kb_ids：agent 挂载的知识库列表，kb 组工具按此闭包重建（空列表=全库旧行为）
    """
    enabled = set(config.get("tools_enabled") or [])
    if not config.get("memory_enabled", True):
        enabled -= {n for n, m in REGISTRY.items() if m["group"] == "memory"}
    if not config.get("kb_enabled", True):
        enabled -= {n for n, m in REGISTRY.items() if m["group"] == "kb"}
    kb_bound = make_kb_tools(config.get("kb_ids") or [])
    out, kb_used = [], 0
    for n, m in REGISTRY.items():
        if n not in enabled:
            continue
        if m["group"] == "kb":
            out.append(kb_bound[kb_used] if kb_used < len(kb_bound) else m["func"])
            kb_used += 1
        else:
            out.append(m["func"])
    return out
