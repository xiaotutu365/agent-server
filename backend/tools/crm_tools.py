"""CRM 业务工具集（示例）。

设计原则：
1. 每个接口一个 @tool，docstring 写给模型看——何时用、参数含义、返回什么。
2. 返回值裁剪：只回传模型需要的字段，避免原始大 JSON 撑爆上下文。
3. 错误信息可读：把接口错误转成人话，模型能据此自我纠错（如换参数重试）。
4. 同类查询可用 action 枚举聚合，控制工具数量。
5. 权限：每个工具从运行时 config 注入当前用户身份（user_id / role），
   - 角色为 admin：可查询全部客户与全公司聚合报表；
   - 角色为 user：仅可查询「归属自己」的客户（下游 CRM 或 Mock 按 owner 校验），
     且禁止查询公司级聚合报表。

对接真实系统时：修改 api_client.request 的 base_url/token 配置，
并把各工具的 path、字段映射替换为公司实际接口定义。
"""

import json
from langchain_core.runnables import RunnableConfig

from langchain_core.tools import tool

from tools.api_client import ApiError, request


def _user_ctx(config: RunnableConfig | None) -> dict:
    """从运行时 config 取出调用方身份；缺省按最小权限（普通用户）处理。"""
    cfg = {}
    if isinstance(config, dict):
        cfg = config.get("configurable", {}) or {}
    return {
        "user_id": cfg.get("user_id"),
        "role": cfg.get("role", "user"),
    }


# ---------- 单接口单工具：语义最清晰，模型调用准确率最高 ----------

@tool
def query_customer(phone: str, config: RunnableConfig = None) -> str:
    """按手机号精确查询客户档案。

    适用场景：用户提供了客户手机号，需要获取该客户的 ID、姓名、会员等级。
    返回: JSON，含 customer_id / name / level / created_at 字段；未找到时返回提示。
    示例: query_customer("13800138000")
    """
    ctx = _user_ctx(config)
    try:
        data = request(
            "GET", "/api/customers/search", params={"phone": phone}, user_ctx=ctx
        )
    except ApiError as exc:
        return f"查询客户失败: {exc}"

    items = data.get("data", [])
    if not items:
        return f"未找到手机号 {phone} 对应的客户。"

    # 裁剪字段：接口原始返回可能有几十个字段，只保留模型需要的
    brief = [
        {
            "customer_id": c.get("id"),
            "name": c.get("name"),
            "level": c.get("memberLevel"),
            "created_at": c.get("createTime", "")[:10],
        }
        for c in items
    ]
    return json.dumps(brief, ensure_ascii=False)


@tool
def list_customer_orders(customer_id: str, status: str = "all", limit: int = 10,
                         config: RunnableConfig = None) -> str:
    """查询某客户的订单列表（按下单时间倒序）。

    参数:
      customer_id: 客户 ID（先用 query_customer 获取）
      status: 订单状态过滤，可选 all / pending / paid / shipped / completed / cancelled
      limit: 返回条数，1-20，默认 10
    返回: JSON 数组，每项含 order_id / status / amount / created_at。
    示例: list_customer_orders("C10086", status="paid", limit=5)
    """
    if status not in {"all", "pending", "paid", "shipped", "completed", "cancelled"}:
        return (f"无效状态 {status}，可选值: "
                "all / pending / paid / shipped / completed / cancelled")

    ctx = _user_ctx(config)
    params = {"customerId": customer_id, "pageSize": min(max(limit, 1), 20)}
    if status != "all":
        params["status"] = status

    try:
        data = request("GET", "/api/orders", params=params, user_ctx=ctx)
    except ApiError as exc:
        return f"查询订单失败: {exc}"

    brief = [
        {
            "order_id": o.get("orderNo"),
            "status": o.get("status"),
            "amount": o.get("payAmount"),
            "created_at": o.get("createTime", "")[:10],
        }
        for o in data.get("data", {}).get("list", [])
    ]
    return json.dumps(brief, ensure_ascii=False) if brief else "该客户暂无符合条件的订单。"


@tool
def create_work_order(customer_id: str, title: str,
                      description: str = "", level: str = "normal",
                      config: RunnableConfig = None) -> str:
    """为某客户创建售后工单。

    参数:
      customer_id: 客户 ID（必填，先用 query_customer 获取）
      title: 工单标题，简明描述问题，如"订单未收到货"
      description: 问题详情（可选）
      level: 紧急程度，可选 normal / urgent，客户明确表达不满或投诉时用 urgent
    返回: 成功时返回工单号；失败时返回原因。
    示例: create_work_order("C10086", "订单未收到货", level="urgent")
    """
    if level not in {"normal", "urgent"}:
        return "level 仅支持 normal 或 urgent。"

    ctx = _user_ctx(config)
    body = {
        "customerId": customer_id,
        "title": title,
        "description": description,
        "priority": level,
    }
    try:
        data = request("POST", "/api/work-orders", json_body=body, user_ctx=ctx)
    except ApiError as exc:
        return f"创建工单失败: {exc}"

    order_no = data.get("data", {}).get("orderNo")
    return f"工单创建成功，工单号: {order_no}" if order_no else f"接口返回异常: {data}"


# ---------- 同类查询聚合：action 枚举控制工具数量 ----------

@tool
def crm_report(action: str, date_from: str = "", date_to: str = "",
               config: RunnableConfig = None) -> str:
    """CRM 统计报表查询（聚合工具）。

    参数:
      action: 报表类型，可选值:
        - sales_daily: 指定区间每日销售额汇总
        - customer_growth: 指定区间新增客户数趋势
        - order_status: 当前各状态订单数量分布（无需日期）
      date_from / date_to: 日期范围，格式 YYYY-MM-DD；action=order_status 时忽略
    示例: crm_report("sales_daily", "2026-10-01", "2026-10-10")

    权限: 销售/客户聚合报表属于公司级数据，仅管理员(role=admin)可查询。
    """
    ctx = _user_ctx(config)
    if ctx["role"] != "admin":
        return ("⛔ 无权限：销售/客户聚合报表为公司级数据，仅管理员可查询。"
                "你可改为查询单个客户的订单或工单。")

    if action not in {"sales_daily", "customer_growth", "order_status"}:
        return "action 仅支持 sales_daily / customer_growth / order_status。"

    params = {}
    if action != "order_status":
        if not date_from or not date_to:
            return "该报表需要提供 date_from 和 date_to（格式 YYYY-MM-DD）。"
        params = {"startDate": date_from, "endDate": date_to}

    path = {
        "sales_daily": "/api/reports/sales-daily",
        "customer_growth": "/api/reports/customer-growth",
        "order_status": "/api/reports/order-status",
    }[action]

    try:
        data = request("GET", path, params=params, user_ctx=ctx)
    except ApiError as exc:
        return f"报表查询失败: {exc}"

    return json.dumps(data.get("data", {}), ensure_ascii=False)


# 供 deep_agent.py 引入
CRM_TOOLS = [query_customer, list_customer_orders, create_work_order, crm_report]
