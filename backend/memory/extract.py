"""记忆自动抽取：对话结束后用默认 chat LLM 提炼 0-3 条陈述句记忆。

后台任务（asyncio.create_task 调用）——任何异常只记日志，绝不外抛。
"""

import asyncio
import json
import logging

from memory import store, vector

logger = logging.getLogger(__name__)

MAX_MEMORIES = 3

EXTRACT_PROMPT = """请从下面这段对话中提取值得长期记住的用户信息。

规则：
- 只输出一个 JSON 字符串数组，不要输出任何其他内容
- 每条为一句第三人称陈述句，例如 "用户偏好简洁的回答"
- 最多 {max_n} 条；没有值得记住的信息时输出 []

对话：
用户：{user}
助手：{assistant}"""


async def _get_llm():
    """默认 chat 模型：优先 model_store 的 llm 默认项；无则回退环境变量（与 deep_agent 同链）。"""
    import os

    from agent.model_store import get_default

    model_name = os.getenv("MODEL_NAME", "deepseek-flash")
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    try:
        m = await get_default("llm")
    except Exception:  # noqa: BLE001
        m = None
    if m:
        model_name = m.get("model") or model_name
        api_key = m.get("api_key") or api_key
        base_url = m.get("base_url") or base_url
    if not model_name:
        return None
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        model_name, model_provider="openai",
        api_key=api_key or "EMPTY", base_url=base_url or None,
        temperature=0, streaming=False,
    )


def _parse_json_array(text) -> list:
    """从 LLM 输出中解析字符串数组；容忍 markdown 包裹/前后缀，失败返回 []。"""
    try:
        text = (text or "").strip()
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return []
        items = json.loads(text[start:end + 1])
        return [it.strip() for it in items if isinstance(it, str) and it.strip()]
    except Exception:  # noqa: BLE001
        return []


async def extract_and_save(user_id: str, thread_id: str, user_text: str, assistant_text: str):
    """抽取并入库（SQLite + Qdrant）。供 main.py 在 SSE done 后 create_task 调用。"""
    try:
        llm = await _get_llm()
        if llm is None:
            return
        prompt = EXTRACT_PROMPT.format(
            max_n=MAX_MEMORIES,
            user=(user_text or "")[:2000],
            assistant=(assistant_text or "")[:2000],
        )
        reply = await asyncio.to_thread(llm.invoke, prompt)
        items = _parse_json_array(getattr(reply, "content", reply))[:MAX_MEMORIES]
        for content in items:
            entry = await store.add_memory(user_id, content, source_thread=thread_id)
            # 同步 embedding/Qdrant 调用放线程池，避免阻塞事件循环
            await asyncio.to_thread(vector.upsert_memory, entry)
        if items:
            logger.info("记忆抽取：user=%s 新增 %d 条", user_id, len(items))
    except Exception:  # noqa: BLE001  # 后台任务静默失败
        logger.exception("记忆抽取失败（已忽略）")
