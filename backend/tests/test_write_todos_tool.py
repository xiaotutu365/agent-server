"""write_todos 计划工具装配：deepagents 0.7.x 不再内置 PlanningMiddleware，
而系统提示词承诺 write_todos、main.py 依赖该工具名产出 plan SSE 事件——
缺失会导致任务清单（PlanPanel/抽屉）整条链路不可用，此处钉住装配契约。"""

import agent.deep_agent as da


def test_write_todos_tool_exists():
    assert da.WRITE_TODOS.name == "write_todos"


def test_assemble_tools_appends_write_todos():
    """无论配置开关如何，计划工具都应装配（框架级能力，不随 tools_enabled 关闭）。"""
    tools = da._assemble_tools({"tools_enabled": [], "memory_enabled": False, "kb_enabled": False})
    assert any(getattr(t, "name", None) == "write_todos" for t in tools)


def test_write_todos_returns_summary():
    out = da.WRITE_TODOS.invoke({
        "todos": [
            {"content": "查看工作区", "status": "completed"},
            {"content": "写入文件", "status": "pending"},
        ]
    })
    assert "2" in out
