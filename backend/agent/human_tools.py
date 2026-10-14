"""人机交互工具：让 agent 在长任务中途主动向用户提问并暂停。

机制：配合 deepagents 的 HumanInTheLoopMiddleware，当 `ask_human` 出现在
`INTERRUPT_TOOLS` 且 allowed_decisions 含 "respond" 时，模型调用本工具后图会
`interrupt()` 挂起，等待前端用 `Command(resume={"decisions":[{"type":"respond",
"message": 用户回答}]})` 恢复——用户的回答直接作为本工具的返回值继续驱动 agent，
工具本身不会真正执行。
"""

from langchain_core.tools import tool


@tool
def ask_human(question: str) -> str:
    """在任务执行过程中需要向用户确认信息或征求意见时调用。

    调用后流程会暂停，等待用户回复；用户的回答会作为本工具的返回结果继续任务。
    适用于：缺少关键参数、需要用户做选择、或想确认方向是否正确再继续。
    示例: ask_human("你希望这份报告用中文还是英文输出？")
    """
    # 实际不会被执行：HITL 的 respond 决策会用用户的回答替代本工具返回。
    return "（等待用户输入，工具未实际执行）"


HUMAN_TOOLS = [ask_human]
