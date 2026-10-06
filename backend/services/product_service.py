from dao import product_dao


def handle(intent: dict) -> dict:
    """根据 AI 识别出的意图，执行对应操作"""
    action = (intent.get("intent") or "").lower()

    if action == "query":
        return _do_query(intent)
    elif action == "create":
        return _do_create(intent)
    elif action == "update":
        return _do_update(intent)
    elif action == "delete":
        return _do_delete(intent)
    elif action == "unknown":
        return _do_unknow()
    else:
        return {"ok": False, "message": f"无法识别的指令：{intent}"}


def _do_query(p: dict) -> dict:
    name = (p.get("name") or "").strip()
    rows = product_dao.query_products(name if name else None)
    if not rows:
        return {"ok": True, "message": "未找到匹配的商品", "data": []}
    return {"ok": True, "message": f"查询到 {len(rows)} 条商品", "data": rows}


def _do_create(p: dict) -> dict:
    name = (p.get("name") or "").strip()
    if not name:
        return {"ok": False, "message": "缺少商品名"}

    price = p.get("price")
    stock = p.get("stock")
    if not isinstance(price, (int, float)) or price < 0:
        return {"ok": False, "message": "价格必须是非负数"}
    if not isinstance(stock, int) or stock < 0:
        return {"ok": False, "message": "库存必须是非负整数"}

    if product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 已存在"}

    try:
        new_id = product_dao.insert_product(name, price, stock)
        return {"ok": True, "message": f"新增成功：{name}", "data": {"id": new_id}}
    except Exception as e:
        return {"ok": False, "message": f"新增失败：{e}"}


def _do_update(p: dict) -> dict:
    name = (p.get("name") or "").strip()
    if not name:
        return {"ok": False, "message": "缺少商品名"}

    if not product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 不存在"}

    fields = {}
    if "price" in p and p["price"] is not None:
        v = p["price"]
        if not isinstance(v, (int, float)) or v < 0:
            return {"ok": False, "message": "价格必须是非负数"}
        fields["price"] = v
    if "stock" in p and p["stock"] is not None:
        v = p["stock"]
        if not isinstance(v, int) or v < 0:
            return {"ok": False, "message": "库存必须是非负整数"}
        fields["stock"] = v

    if not fields:
        return {"ok": False, "message": "没有可修改的字段"}

    try:
        rows = product_dao.update_product(name, fields)
        return {"ok": True, "message": f"修改成功：{name}", "data": {"affected": rows}}
    except Exception as e:
        return {"ok": False, "message": f"修改失败：{e}"}


def _do_delete(p: dict) -> dict:
    name = (p.get("name") or "").strip()
    if not name:
        return {"ok": False, "message": "缺少商品名"}

    product = product_dao.get_by_name(name)
    if not product:
        return {"ok": False, "message": f"商品 {name} 不存在"}

    return {
        "ok": True,
        "need_confirm": True,
        "action": "delete",
        "target": name,
        "message": (
            f"即将删除商品「{name}」"
            f"（价格 ¥{product['price']}，库存 {product['stock']}），确认删除吗？"
        ),
    }
def _do_unknow()->dict:
    return {"ok":True,"message":"ai未能正确解读意思"}