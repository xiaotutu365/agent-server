"""长期记忆工具：基于 LangGraph BaseStore（SQLite 持久化）。

与"会话记忆"（checkpointer，按 thread 隔离）不同，Store 是跨会话、
按用户命名空间隔离的持久 KV：新开会话也能召回之前记住的事实。

命名空间: ("memory", user_id)；user_id 由请求的 configurable 传入。
注意：AsyncSqliteStore 仅支持异步方法（aput/asearch/adelete），故工具均为 async。
"""

from langchain.tools import ToolRuntime
from langchain_core.tools import tool


def _ns(runtime) -> tuple:
    user_id = (runtime.config.get("configurable", {}) or {}).get("user_id", "default")
    return ("memory", user_id)


@tool
async def remember(runtime: ToolRuntime, key: str, value: str) -> str:
    """把值得长期记住的事实写入跨会话记忆库。

    适用：用户偏好、身份信息、常用参数、明确的指示（如"以后都用中文回复"）。
    不适用：一次性任务、临时状态、任何密钥凭证。
    key 用简短英文标识（如 user_name / reply_language），value 一句话描述。
    示例: remember("user_name", "用户叫小明")
    """
    await runtime.store.aput(_ns(runtime), key, {"value": value})
    return f"已记住 [{key}]: {value}"


@tool
async def recall(runtime: ToolRuntime) -> str:
    """列出当前用户的全部长期记忆（key: value 每行一条）。

    在回答涉及用户历史信息的问题前，先调用本工具确认已知记忆。
    """
    items = await runtime.store.asearch(_ns(runtime), limit=100)
    if not items:
        return "（暂无长期记忆）"
    return "\n".join(
        f"- {it.key}: {it.value.get('value', '')}" for it in items
    )


@tool
async def forget(runtime: ToolRuntime, key: str) -> str:
    """删除一条过时的长期记忆（用户说"别再记着X / X作废"时使用）。"""
    await runtime.store.adelete(_ns(runtime), key)
    return f"已遗忘 [{key}]"


MEMORY_TOOLS = [remember, recall, forget]
