"""生成 CRM Mock 数据：15 个客户 + 关联订单。"""

import json
import os
import random

random.seed(42)

NAMES = ["张伟", "李娜", "王芳", "刘洋", "陈静", "杨帆", "赵磊", "黄敏",
         "周杰", "吴倩", "徐强", "孙丽", "马超", "朱琳", "胡斌"]
LEVELS = ["普通", "白银", "黄金", "钻石"]
CITIES = ["杭州", "上海", "北京", "深圳", "成都", "南京", "武汉", "广州"]
STATUSES = ["pending", "paid", "shipped", "completed", "cancelled"]

customers = []
orders = []

for i, name in enumerate(NAMES, start=1):
    cid = f"C{10000 + i}"
    phone = f"138{i:08d}"
    created = f"2026-{random.randint(1, 9):02d}-{random.randint(1, 28):02d} 10:00:00"
    customers.append({
        "id": cid,
        "name": name,
        "phone": phone,
        "memberLevel": random.choice(LEVELS),
        "city": random.choice(CITIES),
        "createTime": created,
        # 冗余字段，模拟真实接口的大返回，用于演示字段裁剪
        "remark": "内部备注字段，模型不应看到",
        "internalScore": random.randint(0, 100),
    })
    for j in range(random.randint(2, 5)):
        orders.append({
            "orderNo": f"SO2026{random.randint(100000, 999999)}",
            "customerId": cid,
            "status": random.choice(STATUSES),
            "payAmount": round(random.uniform(50, 5000), 2),
            "createTime": f"2026-{random.randint(6, 10):02d}-{random.randint(1, 28):02d} 12:30:00",
            "items": [{"sku": f"SKU{random.randint(100, 999)}", "qty": random.randint(1, 3)}],
        })

data = {"customers": customers, "orders": orders, "work_orders": []}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crm_mock.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"customers={len(customers)} orders={len(orders)} -> {out}")
