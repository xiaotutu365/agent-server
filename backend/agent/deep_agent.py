"""Deep Agent 构建：基于 deepagents + LangChain（OpenAI 兼容端点）。"""

import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from agent.human_tools import HUMAN_TOOLS
from agent.memory_tools import MEMORY_TOOLS
from agent.tool_registry import resolve_tools
from tools.crm_tools import CRM_TOOLS
from tools.custom_tools import CUSTOM_TOOLS
from tools.search_tools import SEARCH_TOOLS
from kb.tools import KB_TOOLS

# 默认需要人工介入（HITL）的工具及其允许的决策类型。
# 与 agent/config_store.DEFAULT_CONFIG["hitl"] 保持一致；运行时以各 Agent 配置的 hitl 为准。
# 配合 deepagents 的 HumanInTheLoopMiddleware：当某工具出现在此表且决策含 "respond" 时，
# 调用该工具会令图 interrupt() 挂起，等待前端用 Command(resume=...) 恢复。
INTERRUPT_TOOLS = {
    "create_work_order": ["approve", "reject"],
    "ask_human": ["respond"],
}

SYSTEM_PROMPT = """你是一个深度研究助手（deep agent）。

工作准则：
1. 复杂任务先用 write_todos 拆解计划，再逐步执行。
2. 你可以使用文件系统工具在工作区读写文件（路径以 / 开头，虚拟文件系统）。
3. 需要外部信息时使用 web_search；数学计算用 calculator；单位换算用 unit_convert。
4. 涉及客户、订单、工单、销售报表等 CRM 业务问题时，使用 crm 相关工具
   （query_customer / list_customer_orders / create_work_order / crm_report）。
5. 长期记忆：当用户透露值得跨会话记住的偏好、身份、常用参数或明确指示时，
   调用 remember 写入；回答涉及"我之前说过/我喜欢什么"等历史信息前，
   先调用 recall 确认已知记忆；用户要求作废某条记忆时用 forget。
   注意：不要把一次性任务或任何密钥凭证写入长期记忆。
6. 知识库：当用户问题涉及内部制度、产品文档、FAQ、历史资料、公司规范等
   不在联网范围的知识时，优先用 search_knowledge_base 检索（kb_id 按主题区分，
   如 "policy"、"product"）；检索到的片段请注明来源后再整合作答。
7. 回答使用简洁的中文，给出结论时附上关键依据。
8. 任务执行途中若缺少关键信息、需要用户做选择或确认方向，可调用 ask_human
   向用户提问，等待其回复后再继续（例如"你希望报告用中文还是英文输出？"）。"""

# SQLite 会话持久化文件（多会话历史、上下文记忆均存于此）
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agent_sessions.db"
)


async def _resolve_llm_config(config: dict, model_id: str | None = None):
    """解析本次构建使用的 LLM 配置，返回 (model_name, api_key, base_url, llm_params)。

    优先级（SPEC-session-model-select）：会话覆盖条目(model_id) > 默认 llm 条目
    > Agent 配置 model_name > 环境变量。覆盖条目不存在（已被删除）时回退默认链路。
    llm_params 为模型条目 extra 中的高级参数（温度/TopP/最大Token/惩罚/超时/停止词），
    Agent 级 temperature 优先级更高（兼容既有 Agent 配置）。
    """
    model_name = config.get("model_name") or os.getenv("MODEL_NAME", "deepseek-flash")
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    llm_cfg = None
    try:
        from agent.model_store import get_default as _get_default_model
        from agent.model_store import get_model as _get_model

        llm_cfg = await _get_model(model_id) if model_id else None
        if not llm_cfg:  # 无覆盖 / 覆盖条目已被删除 → 回退全局默认链路
            llm_cfg = await _get_default_model("llm")
        if llm_cfg:
            model_name = llm_cfg.get("model") or model_name
            if llm_cfg.get("api_key"):
                api_key = llm_cfg["api_key"]
            if llm_cfg.get("base_url"):
                base_url = llm_cfg["base_url"]
    except Exception:  # noqa: BLE001
        llm_cfg = None

    # 从所选「大模型」配置的 extra 读取高级参数（温度 / TopP / 最大Token / 惩罚 / 超时 / 停止词）
    llm_params: dict = {}
    if llm_cfg:
        ex = llm_cfg.get("extra")
        if isinstance(ex, dict):
            for _k in ("temperature", "top_p", "max_tokens",
                       "frequency_penalty", "presence_penalty", "timeout", "stop"):
                if _k in ex and ex[_k] not in (None, ""):
                    llm_params[_k] = ex[_k]
    # Agent 级 temperature 优先级更高（兼容既有 Agent 配置）
    if config.get("temperature") not in (None, ""):
        llm_params["temperature"] = config["temperature"]
    return model_name, api_key, base_url, llm_params


async def build_agent(config: dict | None = None, system_prompt: str | None = None,
                      model_id: str | None = None):
    """创建 deepagent（编译后的 LangGraph），带 SQLite 持久化 checkpointer。

    system_prompt 非空时覆盖 config 的 system_prompt，用于 EDA 等多角色
    流水线：每个角色用不同提示词，由调用方按提示词缓存复用同一 graph。

    config 来自 agent/config_store（数据库中的全局配置）：
      - system_prompt / model_name / temperature
      - tools_enabled + memory_enabled/kb_enabled 决定加载哪些工具
      - hitl 决定哪些工具执行前需人工确认（基于 deepagents 内置
        HumanInTheLoopMiddleware）。allowed_decisions 取值：
          approve  批准执行                reject   拒绝执行（可选 message 理由）
          respond  由用户回答代替工具返回   edit     修改工具参数后执行
    model_id 非空时以该模型条目覆盖默认对话模型（会话级模型选择，
    SPEC-session-model-select）；覆盖条目不存在时自动回退默认链路。
    未传入 config 时使用硬编码兜底（便于独立测试）。
    """
    config = config or {}

    # 统一模型配置：会话覆盖条目(model_id) > 默认「大模型」条目 > Agent 配置 > 环境变量
    model_name, api_key, base_url, llm_params = await _resolve_llm_config(config, model_id)

    model_kwargs: dict = {}
    for _k in ("top_p", "max_tokens", "frequency_penalty", "presence_penalty", "timeout"):
        if _k in llm_params:
            try:
                model_kwargs[_k] = int(llm_params[_k]) if _k == "max_tokens" else float(llm_params[_k])
            except (TypeError, ValueError):
                pass
    if llm_params.get("stop"):
        _s = llm_params["stop"]
        model_kwargs["stop"] = [x.strip() for x in str(_s).split(",") if x.strip()]

    model = init_chat_model(
        model_name,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
        temperature=float(llm_params.get("temperature", config.get("temperature", 0.3))),
        streaming=True,
        **model_kwargs,
    )

    # 虚拟文件系统：限制在 backend/workspace 目录内
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workspace = os.path.join(base_dir, "workspace")
    os.makedirs(workspace, exist_ok=True)
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)

    # checkpointer：按 thread_id 持久化会话状态（消息历史、todos 等）
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()

    # store：跨会话、按 user_id 命名空间隔离的长期记忆（独立连接，同一 DB 文件）
    # isolation_level=None：关闭隐式事务，由 Store 自行 BEGIN/COMMIT（否则报
    # "cannot start a transaction within a transaction"）
    store_conn = await aiosqlite.connect(DB_PATH, isolation_level=None)
    store = AsyncSqliteStore(store_conn)
    await store.setup()

    # 工具：根据配置筛选（tools_enabled + 记忆/知识库总开关）
    tools = resolve_tools(config)

    # MCP：并入外部服务器工具（配置在 mcp_servers；加载失败不阻断主流程）
    mcp_cfg = config.get("mcp_servers") or []
    if mcp_cfg:
        try:
            from agent.mcp_tools import load_mcp_tools

            mcp_tools, _ = await load_mcp_tools(mcp_cfg)
            if mcp_tools:
                tools = tools + mcp_tools
                logger.info("已并入 %d 个 MCP 工具", len(mcp_tools))
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP 工具加载失败，已跳过：%s", exc)

    # HITL：仅对「已启用」的工具生效
    enabled_names = {t.name for t in tools}
    interrupt_on = {}
    for t, ds in (config.get("hitl") or {}).items():
        if t in enabled_names:
            interrupt_on[t] = {"allowed_decisions": ds}

    return create_deep_agent(
        model=model,
        system_prompt=system_prompt or config.get("system_prompt") or SYSTEM_PROMPT,
        tools=tools,
        interrupt_on=interrupt_on,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
    )
