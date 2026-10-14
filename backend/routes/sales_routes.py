from flask import Blueprint, request
from dao import sales_dao, product_dao
from response import success, error

bp = Blueprint("sales", __name__, url_prefix="/api")

@bp.route("sales",methods=["GET"])
def get_sales():
    """查询销售记录"""
    name=request.args.get("name")
    name = (name or "").replace(" ", "").strip()
    days=request.args.get("days",type=int)
    row=sales_dao.get_sales(product_name=name,days=days)
    return success(data=row,message=f"共{len(row)}条")

@bp.route("sales",methods=["POST"])
def add_sale():
    """记录一笔销售"""
    body=request.get_json(silent=True)or{}
    name = (body.get("name") or "").replace(" ", "").strip()
    quantity = body.get("quantity")
    unit_price = body.get("unit_price")
    if not name:
        return error("name 不能为空", code=400)
    if not isinstance(quantity, int) or isinstance(quantity,bool) or quantity <= 0:
        return error("quantity 必须是正整数", code=400)
    product = product_dao.get_by_name(name)
    if not product:
        return error(f"商品 {name} 不存在", code=404)
    if quantity > product["stock"]:
        return error(f"库存不足：当前 {product['stock']}，请求 {quantity}", code=400)
    if unit_price is None:
        unit_price = float(product["price"])
    elif not isinstance(unit_price, (int, float)) or isinstance(unit_price,bool) or unit_price < 0:
        return error("unit_price 不合法", code=400)
    try:
        sale_id = sales_dao.record_sale(name, quantity, unit_price)
        new_stock = product["stock"] - quantity
        product_dao.update_product(name, {"stock": new_stock})
        return success(
            data={"sale_id": sale_id, "new_stock": new_stock},
            message=f"已记录销售：{name} × {quantity}",
        )
    except Exception as e:
        return error(f"记录失败：{e}", code=500)

@bp.route("/sales/summary", methods=["GET"])
def sales_summary():
    """销量汇总，支持 ?name=xxx&days=30"""
    name = request.args.get("name")
    name = (name or "").replace(" ", "").strip()
    days = request.args.get("days", type=int)
    total_qty = sales_dao.total_sold(product_name=name, days=days)
    rows = sales_dao.get_sales(product_name=name, days=days)
    total_amount = sum(float(r["total"]) for r in rows)
    return success(data={
        "total_quantity": total_qty,
        "total_amount": round(total_amount, 2),
        "count": len(rows),
    })