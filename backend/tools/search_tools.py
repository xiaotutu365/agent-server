"""联网搜索工具（Tavily，未配置 API Key 时返回提示）。"""

import os

from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索信息。输入搜索关键词，返回相关网页摘要。
    示例: web_search("deepagents langchain 最新特性")"""
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key or api_key.startswith("your"):
        return "联网搜索未启用：请在 backend/.env 中配置 TAVILY_API_KEY。"
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results)
        lines = []
        for r in resp.get("results", []):
            lines.append(f"- [{r.get('title', '')}]({r.get('url', '')})\n  {r.get('content', '')[:300]}")
        return "\n".join(lines) if lines else "未找到相关结果。"
    except Exception as exc:  # noqa: BLE001
        return f"搜索失败: {exc}"


SEARCH_TOOLS = [web_search]
