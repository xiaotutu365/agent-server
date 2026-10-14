"""CRM 本地 Mock 数据服务。

未配置 CRM_BASE_URL 时自动启用，从 backend/data/crm_mock.json 读取数据，
让 CRM 工具链可以在没有真实接口的情况下完整测试。
配置了 CRM_BASE_URL 后本模块不会被调用，走真实接口。
"""

import json
import os
import random
import threading
import time

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "crm_mock.json"
)

_lock = threading.Lock()


class MockError(Exception):
    """Mock 层错误（接口未实现、数据文件缺失等）。"""


def _load() -> dict:
    if not os.path.exists(DATA_PATH):
        raise MockError(f"Mock 数据文件不存在: {DATA_PATH}")
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with _lock:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def handle(method: str, path: str, *, params: dict | None = None,
           json_body: dict | None = None, user_ctx: dict | None = None) -> dict:
    """按 (method, path) 路由到 Mock 数据，返回与真实接口同构的 JSON。

    user_ctx: {"user_id":..., "role":...} 用于演示级归属校验——
      role=admin 放行全部；role=user 仅可访问 owner == user_id 的客户。
    """
    params = params or {}
    json_body = json_body or {}
    data = _load()

    # 归属校验：admin 放行；user 仅能访问「归属自己」的客户
    ctx_role = (user_ctx or {}).get("role", "user")
    ctx_uid = str((user_ctx or {}).get("user_id") or "")

    def _forbidden(cid: str) -> bool:
        if ctx_role == "admin":
            return False
        owner = ""
        for c in data["customers"]:
            if c.get("id") == cid:
                owner = str(c.get("owner", "") or "")
                break
        return owner != ctx_uid

    def _deny(cid: str) -> None:
        if _forbidden(cid):
            raise MockError(f"403: 当前用户无权访问客户 {cid} 的数据（归属校验失败）")

    if method == "GET" and path == "/api/customers/search":
        phone = params.get("phone", "")
        matched = [c for c in data["customers"] if c.get("phone") == phone]
        if ctx_role != "admin":
            owned = [c for c in matched if str(c.get("owner", "") or "") == ctx_uid]
            if matched and not owned:
                raise MockError(
                    "403: 当前用户无权查询该客户（归属校验失败）"
                )
            matched = owned
        return {"data": matched}

    if method == "GET" and path == "/api/orders":
        cid = params.get("customerId", "")
        _deny(cid)
        status = params.get("status")
        page_size = int(params.get("pageSize", 10))
        orders = [o for o in data["orders"] if o.get("customerId") == cid]
        if status:
            orders = [o for o in orders if o.get("status") == status]
        orders.sort(key=lambda o: o.get("createTime", ""), reverse=True)
        return {"data": {"list": orders[:page_size], "total": len(orders)}}

    if method == "POST" and path == "/api/work-orders":
        cid = json_body.get("customerId")
        _deny(cid)
        order_no = f"WO{time.strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        record = {
            "orderNo": order_no,
            "customerId": cid,
            "title": json_body.get("title"),
            "description": json_body.get("description", ""),
            "priority": json_body.get("priority", "normal"),
            "status": "open",
            "createTime": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        data.setdefault("work_orders", []).append(record)
        _save(data)
        return {"data": {"orderNo": order_no}}

    if method == "GET" and path == "/api/reports/sales-daily":
        start, end = params.get("startDate", ""), params.get("endDate", "9999-12-31")
        daily: dict[str, float] = {}
        for o in data["orders"]:
            if o.get("status") == "cancelled":
                continue
            d = o.get("createTime", "")[:10]
            if start <= d <= end:
                daily[d] = round(daily.get(d, 0) + float(o.get("payAmount", 0)), 2)
        rows = [{"date": d, "amount": daily[d]} for d in sorted(daily)]
        return {"data": rows}

    if method == "GET" and path == "/api/reports/customer-growth":
        start, end = params.get("startDate", ""), params.get("endDate", "9999-12-31")
        monthly: dict[str, int] = {}
        for c in data["customers"]:
            m = c.get("createTime", "")[:7]
            if start <= m + "-01" <= end:
                monthly[m] = monthly.get(m, 0) + 1
        rows = [{"month": m, "newCustomers": monthly[m]} for m in sorted(monthly)]
        return {"data": rows}

    if method == "GET" and path == "/api/reports/order-status":
        counts: dict[str, int] = {}
        for o in data["orders"]:
            s = o.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return {"data": counts}

    raise MockError(f"Mock 未实现的接口: {method} {path}")
