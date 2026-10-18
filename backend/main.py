"""FastAPI 服务：以 SSE 流式暴露 deepagent，会话历史持久化于 SQLite。

事件类型（event: 字段）：
- token        LLM 文本增量
- tool_start   工具调用开始（含工具名、入参）
- tool_end     工具调用结束（含结果）
- plan         write_todos 计划更新
- error        异常
- done         本轮结束
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langgraph.types import Command
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from agent.config_store import (
    load_default_config, list_agents, get_agent, create_agent,
    update_agent, delete_agent, DEFAULT_CONFIG,
)
from agent.tool_registry import list_tools, ALL_TOOL_NAMES, get_tool_detail
from agent.model_store import (
    list_models, get_model, get_default, create_model, update_model, delete_model,
)
from agent.thread_meta import (
    get_thread_model, set_thread_model, delete_thread_meta, list_thread_models,
)
from agent.auth import (
    init_users_table, seed_admin, verify_login, create_user, list_users,
    delete_user, encode_token, get_current_user, require_admin,
    init_roles_departments,
    list_roles, create_role, delete_role,
    list_departments, create_department, delete_department, update_user,
    logout_token,
)
from kb.api import router as kb_router
from memory.api import router as memory_router
from flow.api import router as flow_router
from flow.store import init_flow_tables
from memory import extract as memory_extract
from memory.store import init_memories_table
from memory import vector as memory_vector

load_dotenv()

AGENT = None
REBUILD_LOCK = None  # 懒初始化：asyncio.Lock 需在事件循环内创建
AGENT_CACHE: dict = {}            # 按 system_prompt 缓存的 agent（EDA 等多角色流水线复用）
AGENT_CACHE_LOCK = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global AGENT, REBUILD_LOCK, AGENT_CACHE_LOCK
    from agent.deep_agent import build_agent

    REBUILD_LOCK = asyncio.Lock()
    AGENT_CACHE_LOCK = asyncio.Lock()
    await init_users_table()
    await init_roles_departments()
    await seed_admin()
    await init_memories_table()
    await init_flow_tables()
    cfg = await load_default_config()
    AGENT = await build_agent(cfg)
    yield


app = FastAPI(title="DeepAgent Server", lifespan=lifespan)

app.include_router(kb_router, dependencies=[Depends(require_admin)])
app.include_router(memory_router, dependencies=[Depends(require_admin)])
# flow 路由按端点声明权限（CRUD=admin，发起/审批/查询=登录用户），不挂全局 admin
app.include_router(flow_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = ""
    thread_id: str = "default"
    user_id: str = "default"
    resume: dict | None = None  # HITL 恢复：传入上次 interrupt 对应的决策（HITLResponse）
    system_prompt: str | None = None  # 多角色流水线（如 EDA）：指定角色提示词，后端按提示词缓存 agent
    agent_id: str | None = None  # 指定使用某个 Agent（含其 MCP 服务器配置）；为空则用默认 AGENT
    model_id: str | None = None  # 会话级模型选择：""=跟随全局默认（清覆盖）；None=老客户端不改；非空=用该模型并持久化


logger = logging.getLogger("uvicorn.error")


# ── 聊天文件上传（SPEC-chat-ui-evoflow C3.1）──────────────────────────────
# 保存到 agent 工作区（backend/workspace，见 deep_agent.py FilesystemBackend），
# agent 通过 read_file 即可读取；前端发送消息时注入文件路径。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
_UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
UPLOAD_DIR = os.path.join(_UPLOAD_ROOT, "uploads")


def _safe_filename(name: str) -> str | None:
    """文件名安全化：取 basename、去路径/控制字符，空或全非法字符返回 None。"""
    base = os.path.basename(name or "").strip()
    cleaned = "".join(c for c in base if c.isalnum() or c in "._- ()[]（）【】 ")
    cleaned = cleaned.strip(". ")
    return cleaned or None


@app.post("/api/chat/upload", dependencies=[Depends(require_admin)])
async def upload_chat_file(file: UploadFile):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
    safe = _safe_filename(file.filename)
    if not safe:
        raise HTTPException(status_code=400, detail="文件名不安全或为空")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(UPLOAD_DIR, safe)
    if os.path.exists(dest):  # 同名不覆盖：加时间戳后缀
        stem, dot = os.path.splitext(safe)
        dest = os.path.join(UPLOAD_DIR, f"{stem}_{int(time.time())}{dot}")
    with open(dest, "wb") as f:
        f.write(content)
    name = os.path.basename(dest)
    return {"name": name, "path": f"uploads/{name}", "size": len(content)}


async def get_agent_for(system_prompt: str | None, agent_id: str | None = None,
                        model_id: str | None = None):
    """返回本次请求使用的 agent。
    - 指定 system_prompt：按提示词缓存（多角色流水线）。
    - 指定 agent_id：按 id 加载该 Agent 配置并构建（带缓存，含其 MCP 服务器）。
    - 都不指定：返回全局默认 AGENT。
    - 指定 model_id（会话级模型选择）：缓存键附加 ::model:{model_id}，
      不同模型不复用实例；为空时键与既有行为完全一致。
    """
    key_suffix = f"::model:{model_id}" if model_id else ""
    if system_prompt:
        cached = AGENT_CACHE.get(system_prompt + key_suffix)
        if cached is not None:
            return cached
        async with AGENT_CACHE_LOCK:
            cached = AGENT_CACHE.get(system_prompt + key_suffix)
            if cached is not None:
                return cached
            from agent.deep_agent import build_agent
            agent = await build_agent(await load_default_config(), system_prompt=system_prompt,
                                      **({"model_id": model_id} if model_id else {}))
            AGENT_CACHE[system_prompt + key_suffix] = agent
            return agent
    if agent_id:
        key = f"agent:{agent_id}{key_suffix}"
        cached = AGENT_CACHE.get(key)
        if cached is not None:
            return cached
        async with AGENT_CACHE_LOCK:
            cached = AGENT_CACHE.get(key)
            if cached is not None:
                return cached
            cfg = await get_agent(agent_id)
            if not cfg:
                return AGENT
            from agent.deep_agent import build_agent
            agent = await build_agent(cfg, **({"model_id": model_id} if model_id else {}))
            AGENT_CACHE[key] = agent
            return agent
    if model_id:  # 无 prompt/agent 但指定会话模型：按模型构建（缓存键 default::model:{id}）
        key = f"default{key_suffix}"
        cached = AGENT_CACHE.get(key)
        if cached is not None:
            return cached
        async with AGENT_CACHE_LOCK:
            cached = AGENT_CACHE.get(key)
            if cached is not None:
                return cached
            from agent.deep_agent import build_agent
            agent = await build_agent(await load_default_config(), model_id=model_id)
            AGENT_CACHE[key] = agent
            return agent
    return AGENT


@app.get("/api/agents")
async def list_agents_public(user: dict = Depends(get_current_user)):
    """已登录用户可用的 Agent 列表（仅摘要：id/name/is_default），供聊天页选择。"""
    ags = await list_agents()
    return {"agents": [
        {"id": a["id"], "name": a["name"], "is_default": bool(a.get("is_default", False))}
        for a in ags
    ]}


@app.get("/api/models/chat")
async def list_chat_models(user: dict = Depends(get_current_user)):
    """聊天页「模型」下拉候选（SPEC-session-model-select）。

    普通用户可访问；仅 type=llm 条目摘要（id/name/model/is_default），
    不暴露 api_key/base_url——密钥管理仍在 /api/admin/models。
    """
    models = await list_models("llm")
    return {"models": [
        {"id": m["id"], "name": m["name"], "model": m["model"],
         "is_default": bool(m.get("is_default", False))}
        for m in models
    ]}


class AgentConfig(BaseModel):
    """后台 Agent 配置（多 Agent，每条可独立配置）。"""
    name: str = "默认 DeepAgent"
    system_prompt: str = ""
    model_name: str = "deepseek-flash"
    temperature: float = 0.3
    tools_enabled: list[str] = []
    hitl: dict[str, list[str]] = {}
    memory_enabled: bool = True
    kb_enabled: bool = True
    kb_ids: list[str] = []
    mcp_servers: list[dict] = []
    is_default: bool = False
    id: str = ""


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_kb_citations(output: str) -> list:
    """从 kb 工具的结构化输出提取引用来源 [{file, kb_id, chunk_idx, score}]。"""
    try:
        data = json.loads(output)
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []
        cits = []
        for r in results:
            if isinstance(r, dict) and r.get("source"):
                cits.append({
                    "file": r.get("source"),
                    "kb_id": r.get("kb_id", ""),
                    "chunk_idx": r.get("chunk_idx", 0),
                    "score": r.get("score"),
                })
        return cits
    except Exception:  # noqa: BLE001
        return []


def _truncate(text: str, limit: int = 2000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "...(截断)"


def _extract_interrupt_requests(state) -> list:
    """从 LangGraph state（或兼容的测试桩）中提取 HITL 中断请求列表。

    真实 state 形态：state.tasks[].interrupts[].value（即 HumanInTheLoopMiddleware
    构造的 HITLRequest：含 action_requests / review_configs）。同时兼容以
    顶层 .interrupts / {"interrupts": [...]} 直接暴露的中断列表（测试桩）。
    """
    if state is None:
        return []
    # 真实 state：中断挂在 tasks 之下
    tasks = getattr(state, "tasks", None)
    if tasks is None and isinstance(state, dict):
        tasks = state.get("tasks")
    candidates = []
    if tasks:
        for task in tasks:
            interrupts = getattr(task, "interrupts", None)
            if interrupts is None and isinstance(task, dict):
                interrupts = task.get("interrupts")
            if interrupts:
                candidates.extend(interrupts)
    else:
        # 兼容顶层直接暴露 interrupts 的形态（测试桩）
        interrupts = getattr(state, "interrupts", None)
        if interrupts is None and isinstance(state, dict):
            interrupts = state.get("interrupts")
        if interrupts:
            candidates.extend(interrupts)
    requests = []
    for intr in candidates:
        val = getattr(intr, "value", None)
        if val is None and isinstance(intr, dict):
            val = intr.get("value")
        if val is not None:
            requests.append(val)
    return requests


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": os.getenv("MODEL_NAME", "")}


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    user = await verify_login(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": encode_token(user), "user": user}


_bearer = HTTPBearer(auto_error=False)


@app.post("/api/auth/logout")
async def logout(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """登出：将当前 Bearer token 加入服务端黑名单（内存态）。未携带凭证时幂等成功。"""
    if creds and creds.credentials:
        await logout_token(creds.credentials)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}


# ---------- 会话管理 ----------

def _db_path() -> str:
    from agent.deep_agent import DB_PATH
    return DB_PATH


def _msg_text(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return content or ""


@app.get("/api/threads")
async def list_threads(user: dict = Depends(get_current_user)):
    """会话列表（按当前用户隔离）：thread_id / 标题 / 更新时间 / 会话模型覆盖。"""
    prefix = f"u{user['id']}:"
    async with aiosqlite.connect(_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT thread_id, MAX(checkpoint_id) AS ckpt "
            "FROM checkpoints WHERE thread_id LIKE ? GROUP BY thread_id ORDER BY ckpt DESC",
            (prefix + "%",),
        )
        rows = await cur.fetchall()

    metas = await list_thread_models()  # 一次性取全量覆盖（thread_id → model_id）
    threads = []
    for r in rows:
        cfg = {"configurable": {"thread_id": r["thread_id"]}}
        state = await AGENT.aget_state(cfg)
        title = "新会话"
        ts = ""
        if state and state.values:
            ts = (state.created_at or "") if hasattr(state, "created_at") else ""
            for m in state.values.get("messages", []):
                if getattr(m, "type", "") == "human" and _msg_text(m):
                    title = _msg_text(m)[:30]
                    break
        threads.append({
            "thread_id": r["thread_id"][len(prefix):],
            "title": title,
            "updated_at": ts,
            "model_id": metas.get(r["thread_id"], ""),
        })
    return {"threads": threads}


@app.get("/api/threads/{thread_id}/messages")
async def thread_messages(thread_id: str, user: dict = Depends(get_current_user)):
    """恢复会话消息（仅 user/assistant 文本），供前端渲染历史。"""
    cfg = {"configurable": {"thread_id": f"u{user['id']}:{thread_id}"}}
    state = await AGENT.aget_state(cfg)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="会话不存在")

    msgs = []
    for m in state.values.get("messages", []):
        t = getattr(m, "type", "")
        if t == "human":
            msgs.append({"role": "user", "content": _msg_text(m)})
        elif t == "ai" and _msg_text(m):
            msgs.append({"role": "assistant", "content": _msg_text(m)})
    return {"messages": msgs}


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str, user: dict = Depends(get_current_user)):
    """删除会话（checkpoints/writes 均按 thread_id 级联清理，含模型覆盖记录）。"""
    lg = f"u{user['id']}:{thread_id}"
    await AGENT.checkpointer.adelete_thread(lg)
    await delete_thread_meta(lg)
    return {"status": "deleted", "thread_id": thread_id}


async def _resolve_session_model(lg_thread: str, req_model_id: str | None) -> str | None:
    """解析本次消息实际生效的会话模型（SPEC-session-model-select）。

    req_model_id 语义：
      - None  老客户端/未携带：沿用会话覆盖，无则跟随全局默认
      - ""    前端选了「默认（跟随全局）」：清除会话覆盖
      - 非空  使用该模型并持久化为会话覆盖
    模型不存在或非 llm 类型 → 清理覆盖并回退默认（不中断会话）。
    """
    if req_model_id == "":
        await delete_thread_meta(lg_thread)
        return None

    async def _valid(mid):
        if not mid:
            return False
        m = await get_model(mid)
        return bool(m and m.get("type") == "llm")

    if req_model_id is not None:
        if await _valid(req_model_id):
            await set_thread_model(lg_thread, req_model_id)
            return req_model_id
        await delete_thread_meta(lg_thread)
        logger.warning("会话 %s 请求的模型 %s 无效，回退全局默认", lg_thread, req_model_id)
        return None

    stored = await get_thread_model(lg_thread)
    if await _valid(stored):
        return stored
    if stored:
        await delete_thread_meta(lg_thread)
        logger.warning("会话 %s 覆盖的模型 %s 已失效，回退全局默认", lg_thread, stored)
    return None


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    async def event_gen():
        assistant_text = ""  # 聚合本轮 assistant 回复全文，done 后供记忆抽取
        lg_thread = f"u{user['id']}:{req.thread_id or 'default'}"
        # 会话级模型选择（SPEC-session-model-select）：解析失败不阻断会话
        try:
            model_id = await _resolve_session_model(lg_thread, req.model_id)
        except Exception:  # noqa: BLE001
            model_id = None
        agent = await get_agent_for(req.system_prompt, req.agent_id, model_id)
        config = {
            "configurable": {
                "thread_id": lg_thread,
                "user_id": str(user["id"]),
                "role": user["role"],
            },
            "recursion_limit": 100,
        }
        # 写入当前用户身份，供 MCP 工具的越界闸读取
        from agent.mcp_tools import set_user_ctx

        set_user_ctx(user["id"], user["role"])
        # 恢复中断：带 resume 时以 Command 恢复挂起的图；否则作为新消息进入
        if req.resume is not None:
            inputs = Command(resume=req.resume)
        else:
            inputs = {"messages": [{"role": "user", "content": req.message}]}
            # 记忆注入：检索到的用户记忆以 SystemMessage 前插（检索异常按无记忆处理）
            try:
                mems = await asyncio.to_thread(
                    memory_vector.search, str(user["id"]), req.message, 5)
                if mems:
                    lines = "\n".join(f"- {m.get('content', '')}" for m in mems)
                    inputs["messages"].insert(0, SystemMessage(
                        content=f"以下是关于该用户的已知记忆（供参考，勿主动罗列）：\n{lines}"))
            except Exception:  # noqa: BLE001
                pass
        try:
            async for ev in agent.astream_events(inputs, config=config, version="v2"):
                kind = ev["event"]
                name = ev.get("name", "")

                if kind == "on_chat_model_stream":
                    chunk = ev["data"].get("chunk")
                    text = getattr(chunk, "content", "") or ""
                    if isinstance(text, list):  # 部分模型返回内容块列表
                        text = "".join(
                            b.get("text", "") for b in text
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    if text:
                        assistant_text += text
                        yield sse("token", {"content": text})

                elif kind == "on_tool_start":
                    tool_input = ev["data"].get("input", {})
                    if name == "write_todos":
                        todos = tool_input.get("todos", []) if isinstance(tool_input, dict) else []
                        yield sse("plan", {"todos": todos})
                    yield sse("tool_start", {
                        "tool": name,
                        "input": _truncate(json.dumps(
                            tool_input, ensure_ascii=False, default=str), 1000),
                    })

                elif kind == "on_tool_end":
                    output = ev["data"].get("output", "")
                    if hasattr(output, "content"):
                        output = output.content
                    if isinstance(output, list):
                        output = "".join(
                            b.get("text", "") for b in output
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    payload = {"tool": name, "output": _truncate(str(output))}
                    # kb 工具：从结构化输出提取引用来源，供前端在回答下方渲染
                    if name == "search_knowledge_base":
                        cits = _extract_kb_citations(str(output))
                        if cits:
                            payload["citations"] = cits
                    yield sse("tool_end", payload)

                # 注：interrupt 发生在 middleware 的 after_model 钩子里，astream_events
                # 不会 emit on_interrupt 事件，也不产出任何后续事件（图直接挂起）。
                # 改为在循环结束后用 aget_state 检测挂起状态，见下方 else 分支。

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            yield sse("error", {"message": str(exc)})
        else:
            # 检测图是否因 HITL 挂起：从 state 提取每个 interrupt 的 value
            # （即 HumanInTheLoopMiddleware 构造的 HITLRequest：含 action_requests/review_configs）
            try:
                state = await agent.aget_state(config)
                interrupts = _extract_interrupt_requests(state)
                if interrupts:
                    yield sse("interrupt", {"requests": interrupts})
            except Exception as exc:  # noqa: BLE001
                yield sse("error", {"message": f"检测中断失败: {exc}"})

        finally:
            yield sse("done", {})
            # done 后后台抽取记忆（HITL 恢复轮不抽取）；后台任务静默失败
            if req.resume is None and (req.message or "").strip():
                asyncio.create_task(memory_extract.extract_and_save(
                    str(user["id"]), req.thread_id or "default",
                    req.message, assistant_text))

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 后台：多 Agent 管理（需管理员） ----------

@app.get("/api/admin/agents")
async def list_admin_agents(_: dict = Depends(require_admin)):
    """Agent 列表（摘要）。"""
    return {"agents": await list_agents()}


@app.get("/api/admin/agents/template")
async def agent_template(_: dict = Depends(require_admin)):
    """新建 Agent 的默认草稿（不含 id）。"""
    return {"agent": dict(DEFAULT_CONFIG)}


@app.get("/api/admin/agents/{agent_id}")
async def get_admin_agent(agent_id: str, _: dict = Depends(require_admin)):
    """Agent 详情 + 按分组组织的可用工具目录。"""
    agent = await get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"agent": agent, "tool_groups": list_tools()}


@app.post("/api/admin/agents")
async def create_admin_agent(body: AgentConfig, _: dict = Depends(require_admin)):
    """新增 Agent，返回创建后的完整配置。"""
    agent = await create_agent(body.model_dump(exclude={"id"}))
    return {"agent": agent, "tool_groups": list_tools()}


@app.put("/api/admin/agents/{agent_id}")
async def update_admin_agent(agent_id: str, body: AgentConfig, _: dict = Depends(require_admin)):
    """更新 Agent；若为默认则热重建聊天用的全局 AGENT。"""
    cfg = await update_agent(agent_id, body.model_dump())
    if not cfg:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    if cfg["is_default"]:
        global AGENT
        async with REBUILD_LOCK:
            from agent.deep_agent import build_agent

            AGENT = await build_agent(cfg)
    # 聊天页恒带 agent_id → 走 AGENT_CACHE；配置变更后必须失效，否则热重建不生效
    # （含按 system_prompt 缓存的条目：它们内嵌默认 Agent 配置与 MCP 服务器）。
    AGENT_CACHE.clear()
    return {"agent": cfg, "tool_groups": list_tools()}


@app.post("/api/admin/agents/{agent_id}/set-default")
async def set_default_agent(agent_id: str, _: dict = Depends(require_admin)):
    """将该 Agent 设为默认（聊天固定使用），并热重建。"""
    cfg = await update_agent(agent_id, {"is_default": True})
    if not cfg:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    global AGENT
    async with REBUILD_LOCK:
        from agent.deep_agent import build_agent

        AGENT = await build_agent(cfg)
    AGENT_CACHE.clear()
    return {"agent": cfg}


@app.delete("/api/admin/agents/{agent_id}")
async def delete_admin_agent(agent_id: str, _: dict = Depends(require_admin)):
    """删除 Agent；禁止删最后一个；若删的是默认且还有其它则自动改默认并热重建。"""
    try:
        result = await delete_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result["rebuild"]:
        global AGENT
        async with REBUILD_LOCK:
            from agent.deep_agent import build_agent

            AGENT = await build_agent(await load_default_config())
    AGENT_CACHE.pop(f"agent:{agent_id}", None)
    return {"status": "deleted", **result}


# ---------- 后台：MCP 服务器工具发现（需管理员） ----------

@app.post("/api/admin/mcp/discover")
async def discover_mcp(servers: list[dict], _: dict = Depends(require_admin)):
    """临时连接给定 MCP 服务器配置，返回它们暴露的工具清单（不持久化、不并入 agent）。

    用于后台配置页「测试连接 / 预览工具」。servers 元素格式同 agent 配置的 mcp_servers。
    """
    from agent.mcp_tools import load_mcp_tools

    try:
        tools, _ = await load_mcp_tools(servers, apply_policy=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"MCP 连接失败: {exc}")
    return {
        "tools": [
            {
                "name": t.name,
                "description": (t.description or "").strip().split("\n")[0],
            }
            for t in tools
        ]
    }


# ---------- 后台：工具目录（需管理员） ----------

@app.get("/api/admin/tools")
async def admin_list_tools(_: dict = Depends(require_admin)):
    """按分组返回全部已注册工具目录（只读），供后台「工具列表」页展示。"""
    groups = list_tools()
    total = sum(len(g["tools"]) for g in groups)
    return {"groups": groups, "total": total}


@app.get("/api/admin/tools/{tool_name}")
async def admin_tool_detail(tool_name: str, _: dict = Depends(require_admin)):
    """单个工具的完整详情（提示词 / 参数 schema）。"""
    detail = get_tool_detail(tool_name)
    if not detail:
        raise HTTPException(status_code=404, detail="工具不存在")
    return detail


# ---------- 后台：模型配置（需管理员） ----------

@app.get("/api/admin/models")
async def admin_list_models(type: str | None = None, _: dict = Depends(require_admin)):
    """列出模型配置；可按 type（llm/embedding/rerank）过滤。"""
    return {"models": await list_models(type)}


@app.post("/api/admin/models")
async def admin_create_model(body: dict, _: dict = Depends(require_admin)):
    """新增模型配置（大模型/嵌入/重排）。"""
    try:
        m = await create_model(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"model": m}


@app.put("/api/admin/models/{model_id}")
async def admin_update_model(model_id: str, body: dict, _: dict = Depends(require_admin)):
    """更新模型配置。"""
    try:
        m = await update_model(model_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    # 模型配置变更必须失效 agent 缓存（含会话级 ::model: 键），否则旧配置实例一直被复用
    AGENT_CACHE.clear()
    return {"model": m}


@app.delete("/api/admin/models/{model_id}")
async def admin_delete_model(model_id: str, _: dict = Depends(require_admin)):
    """删除模型配置。"""
    result = await delete_model(model_id)
    AGENT_CACHE.clear()  # 同上：删除后清理按模型缓存的实例，会话覆盖在使用时自动回退默认
    return result


@app.post("/api/admin/models/test")
async def admin_test_model_body(body: dict, _: dict = Depends(require_admin)):
    """按提交的配置（未保存也可）探测连通性。"""
    from agent.model_store import test_model_connection

    return await test_model_connection(body)


@app.post("/api/admin/models/{model_id}/test")
async def admin_test_model_id(model_id: str, _: dict = Depends(require_admin)):
    """按已保存的配置（含密钥）探测连通性。"""
    from agent.model_store import get_model, test_model_connection

    m = await get_model(model_id)
    if not m:
        raise HTTPException(status_code=404, detail="模型不存在")
    cfg = {
        "type": m.get("type"), "base_url": m.get("base_url"), "model": m.get("model"),
        "dim": m.get("dim") or 0, "api_key": m.get("api_key") or "", "extra": m.get("extra") or {},
    }
    return await test_model_connection(cfg)


# ---------- 后台：用户管理（需管理员） ----------

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    role_id: str | None = None
    department_id: str | None = None
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = None
    role_id: str | None = None
    department_id: str | None = None
    password: str | None = None
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None


@app.get("/api/admin/users")
async def admin_list_users(_: dict = Depends(require_admin)):
    """用户列表（不含密码哈希；含 role_name / department_name 关联名）。"""
    return {"users": await list_users()}


@app.post("/api/admin/users")
async def admin_create_user(body: CreateUserRequest, _: dict = Depends(require_admin)):
    """管理员创建用户（关联 role_id / department_id，字段校验见 agent.auth）。"""
    try:
        u = await create_user(
            body.username, body.password, body.role, body.role_id, body.department_id,
            email=body.email, phone=body.phone, full_name=body.full_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user": u}


@app.put("/api/admin/users/{uid}")
async def admin_update_user(uid: str, body: UpdateUserRequest, _: dict = Depends(require_admin)):
    """更新用户角色 / 部门 / 密码 / 邮箱 / 电话 / 姓名。"""
    try:
        u = await update_user(
            uid, body.role, body.role_id, body.department_id, body.password,
            email=body.email, phone=body.phone, full_name=body.full_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": u}


@app.delete("/api/admin/users/{uid}")
async def admin_delete_user(uid: str, current: dict = Depends(require_admin)):
    """删除用户（禁止删除自己，禁止删除最后一个管理员）。"""
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录的账号")
    try:
        ok = await delete_user(uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "deleted", "id": uid}


# ---------- 后台：角色管理（需管理员） ----------

class RoleRequest(BaseModel):
    name: str
    key: str
    description: str = ""


@app.get("/api/admin/roles")
async def admin_list_roles(_: dict = Depends(require_admin)):
    """角色列表。"""
    return {"roles": await list_roles()}


@app.post("/api/admin/roles")
async def admin_create_role(body: RoleRequest, _: dict = Depends(require_admin)):
    """新增角色（key 唯一，作为权限标识）。"""
    try:
        r = await create_role(body.name, body.key, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"role": r}


@app.delete("/api/admin/roles/{rid}")
async def admin_delete_role(rid: str, _: dict = Depends(require_admin)):
    """删除角色（内置 admin/user 不可删；其下用户回退为普通用户）。"""
    try:
        ok = await delete_role(rid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"status": "deleted", "id": rid}


# ---------- 后台：部门管理（需管理员） ----------

class DepartmentRequest(BaseModel):
    name: str
    description: str = ""


@app.get("/api/admin/departments")
async def admin_list_departments(_: dict = Depends(require_admin)):
    """部门列表。"""
    return {"departments": await list_departments()}


@app.post("/api/admin/departments")
async def admin_create_department(body: DepartmentRequest, _: dict = Depends(require_admin)):
    """新增部门。"""
    try:
        d = await create_department(body.name, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"department": d}


@app.delete("/api/admin/departments/{did}")
async def admin_delete_department(did: str, _: dict = Depends(require_admin)):
    """删除部门（其下用户 department_id 置空）。"""
    ok = await delete_department(did)
    if not ok:
        raise HTTPException(status_code=404, detail="部门不存在")
    return {"status": "deleted", "id": did}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", "8000")))
