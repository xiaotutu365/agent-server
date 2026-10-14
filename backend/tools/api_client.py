"""统一 HTTP 客户端：base_url、鉴权、超时、重试、错误收敛。

所有业务工具共用这一层，工具函数内只写业务语义。
"""

import os
import time

import httpx


class ApiError(Exception):
    """接口调用失败（业务/HTTP 层错误）。"""


def request(method: str, path: str, *, params: dict | None = None,
            json_body: dict | None = None, timeout: float = 10.0,
            retries: int = 2, user_ctx: dict | None = None) -> dict:
    """发起 HTTP 请求，返回解析后的 JSON。

    - 未配置 CRM_BASE_URL 时自动回退到本地 Mock 数据（tools/mock_store.py）
    - 4xx/5xx 抛出 ApiError（含状态码与响应片段，便于模型自我纠错）
    - 超时/连接错误指数退避重试
    - user_ctx: 形如 {"user_id": "...", "role": "admin|user"}，用于：
        * 透传身份给真实 CRM（X-User-Id / X-User-Role 头），由下游做数据归属校验；
        * 在 Mock 模式下做演示级归属校验。
    """
    base_url = os.getenv("CRM_BASE_URL", "").rstrip("/")
    if not base_url:
        from tools import mock_store

        try:
            return mock_store.handle(
                method, path, params=params, json_body=json_body, user_ctx=user_ctx
            )
        except mock_store.MockError as exc:
            raise ApiError(str(exc))

    token = os.getenv("CRM_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # 透传调用方身份，真实 CRM 据此做行级/租户级归属校验（保证不越界）
    if user_ctx:
        if user_ctx.get("user_id"):
            headers["X-User-Id"] = str(user_ctx["user_id"])
        if user_ctx.get("role"):
            headers["X-User-Role"] = user_ctx["role"]
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            resp = httpx.request(
                method, f"{base_url}{path}",
                params=params, json=json_body, headers=headers, timeout=timeout,
            )
            if resp.status_code >= 400:
                raise ApiError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        except ApiError:
            raise  # 业务错误不重试
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))

    raise ApiError(f"网络异常（已重试 {retries} 次）: {last_exc}")
