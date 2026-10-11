from email import message

from dao import product_dao, purchases_dao, sales_dao


# ============ CRUD ============

def query_products(name: str = "") -> dict:
    """查询商品。传 name 模糊查询，不传则查全部。"""
    rows = product_dao.query_products(name if name else None)
    return {"ok": True, "count": len(rows), "data": rows}


def create_product(name: str, price: float = 0, stock: int = 0) -> dict:
    """新增商品。如果用户没给价格或库存，你要自己生成合理值。"""
    if not name:
        return {"ok": False, "message": "缺少商品名"}
    if product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 已存在"}
    new_id = product_dao.insert_product(name, price, stock)
    return {"ok": True, "id": new_id, "message": f"新增成功：{name}"}


def update_product(name: str, price: float = None, stock: int = None) -> dict:
    """修改商品的价格或库存。"""
    if not product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 不存在"}
    fields = {}
    if price is not None:
        fields["price"] = price
    if stock is not None:
        fields["stock"] = stock
    if not fields:
        return {"ok": False, "message": "没有可修改的字段"}
    rows = product_dao.update_product(name, fields)
    return {"ok": True, "affected": rows, "message": f"修改成功：{name}"}


def delete_product(name: str) -> dict:
    """删除商品（需要用户确认）。"""
    if not product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 不存在"}
    return {
        "ok": True,
        "need_confirm": True,
        "action": "delete",
        "target": name,
        "message": f"即将删除商品「{name}」，确认吗？",
    }

def apply_discount(name:str,rate:float)->dict:
    """给指定的商品打折
        使用场景：用户输入为打折的时候使用，有具体减少数值请使用update_product
        参数：
        name:商品名
        rate：打折比例，0~1 之间。0.8 表示八折（即原价 × 0.8），
              0.5 表示半价，0.9 表示九折。
              如果用户输入的打折倍数不清楚、有误要提示并且再次询问
        返回：打折后的新价格
    """
    if rate<=0 or rate>=1:
        return {"ok":False,"message":"打折倍数不正确"}
    product =product_dao.get_by_name(name)
    if not product :
        return {"ok":False,"message":"打折的商品不存在",}
    else:
        return {"ok":True,"need_confirm":True,"action":"discount","target":name,
                "message":f"将要进行打折的商品：{name},价格将变成{float(product["price"])*rate}确定吗?",
                "data":float(product["price"])*rate}
# =========== sale ===============
def record_sale(product_name: str, quantity: int, unit_price: float = None) -> dict:
    """
    记录一笔销售，并减少库存。
    使用场景：
        用户说"卖了"、"出售"、"卖出"、"卖掉了 X 个 Y" 时使用。
    参数：
        product_name: 商品名。
        quantity: 销售数量（正整数）。
        unit_price: 单价（可选，不传用商品当前价）。
    返回：
        销售记录 ID + 剩余库存。
    """
    if not product_name:
        return {"ok": False, "message": "缺少商品名"}
    if not isinstance(quantity, int) or quantity <= 0:
        return {"ok": False, "message": "售出数量必须是正整数"}
    product = product_dao.get_by_name(product_name)
    if not product:
        return {"ok": False, "message": f"商品 {product_name} 不存在"}
    if quantity > product["stock"]:
        return {"ok": False, "message": f"库存不足：当前 {product['stock']}，请求 {quantity}"}
    if unit_price is None:
        unit_price = float(product["price"])
    elif not isinstance(unit_price, (int, float)) or unit_price < 0:
        return {"ok": False, "message": "售出单价不合法"}
    try:
        sale_id = sales_dao.record_sale(product_name, quantity, unit_price)
        new_stock = product["stock"] - quantity
        product_dao.update_product(product_name, {"stock": new_stock})
        return {
            "ok": True,
            "sale_id": sale_id,
            "new_stock": new_stock,
            "message": f"已记录销售：{product_name} × {quantity}，剩余库存 {new_stock}",
        }
    except Exception as e:
        return {"ok": False, "message": f"记录失败：{e}"}
def query_sales(name: str = None, days: int = None) -> dict:
    """
    查询销售记录。

    使用场景：用户说"卖了什么"、"销售记录"、"昨天卖了啥"时使用。

    参数：
        name: 商品名（可选，不传查全部）。
        days: 最近多少天（可选，不传查全部时间）。

    返回：销售记录列表。
    """
    rows = sales_dao.get_sales(product_name=name, days=days)
    return {
        "ok": True,
        "count": len(rows),
        "data": rows,
        "message": f"共 {len(rows)} 条销售记录",
    }
def sales_report(name: str = None, days: int = 7) -> dict:
    """
    销售报告 / 销售统计。
    使用场景：用户说"销售情况"、"卖了多少钱"、"这周业绩"时使用。
    参数：
        name: 商品名（可选，不传查全部）。
        days: 最近多少天（默认 7）。
    返回：销售总件数、总金额、订单数。
    """
    rows = sales_dao.get_sales(product_name=name, days=days)
    total_qty = sales_dao.total_sold(product_name=name, days=days)
    total_amount = sum(float(r["total"]) for r in rows)
    return {
        "ok": True,
        "count": len(rows),
        "total_quantity": total_qty,
        "total_amount": round(total_amount, 2),
        "data": rows[:20],       # 最多 20 条明细
        "message": (
            f"最近 {days} 天：{len(rows)} 笔订单，"
            f"共 {total_qty} 件，¥{round(total_amount, 2)}"
        ),
    }
# =========== purchases ===========
def record_purchase(product_name: str, quantity: int, unit_price: float = None) -> dict:
    """
    记录一笔进货，并增加库存。

    使用场景：用户说"进了"、"进货"、"补货 X 个 Y"时使用。

    参数：
        product_name: 商品名。
        quantity: 数量（正整数）。
        unit_price: 进货单价（可选）。
    """
    if not product_name:
        return {"ok": False, "message": "缺少商品名"}
    if not isinstance(quantity, int) or quantity <= 0:
        return {"ok": False, "message": "数量必须是正整数"}
    product = product_dao.get_by_name(product_name)
    if not product:
        return {"ok": False, "message": f"商品 {product_name} 不存在"}
    if unit_price is None:
        unit_price = float(product["price"])
    elif not isinstance(unit_price, (int, float)) or unit_price < 0:
        return {"ok": False, "message": "进货单价不合法"}
    try:
        purchase_id = purchases_dao.record_purchase(product_name, quantity, unit_price)
        new_stock = product["stock"] + quantity
        product_dao.update_product(product_name, {"stock": new_stock})
        return {
            "ok": True,
            "purchase_id": purchase_id,
            "new_stock": new_stock,
            "message": f"已记录进货：{product_name} × {quantity}，剩余库存 {new_stock}",
        }
    except Exception as e:
        return {"ok": False, "message": f"记录失败：{e}"}
def query_purchases(name: str = None, days: int = None) -> dict:
    """
    查询进货记录。

    使用场景：用户说"进了什么"、"进货记录"、"最近补货"时使用。

    参数：
        name: 商品名（可选）。
        days: 最近多少天（可选）。

    返回：进货记录列表。
    """
    rows = purchases_dao.get_purchase(product_name=name, days=days)
    return {
        "ok": True,
        "count": len(rows),
        "data": rows,
        "message": f"共 {len(rows)} 条进货记录",
    }




# ============ 工具注册表 ============

TOOL_FUNCTIONS = {
    # 商品
    "query_products": query_products,
    "create_product": create_product,
    "update_product": update_product,
    "delete_product": delete_product,
    "apply_discount": apply_discount,

    # 销售
    "record_sale": record_sale,
    "query_sales": query_sales,
    "sales_report": sales_report,

    # 进货
    "record_purchase": record_purchase,
    "query_purchases": query_purchases,
}

# 传给 Ollama 的工具列表
TOOLS_FOR_AI = list(TOOL_FUNCTIONS.values())