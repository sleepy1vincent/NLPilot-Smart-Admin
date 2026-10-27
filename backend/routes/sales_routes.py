from flask import Blueprint, request
from dao import sales_dao
from response import success, error
from services.tools import record_sale as _record_sale

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
    """
    记录一笔销售。

    业务逻辑（库存检查 / 写记录 / 扣库存 / 事务 / 行锁）全部在 services.tools.record_sale 里，
    这里只负责：解析请求 -> 做参数格式校验 -> 把业务错误码翻译成 HTTP 状态码。
    """
    body=request.get_json(silent=True)or{}
    name = body.get("name")
    quantity = body.get("quantity")
    unit_price = body.get("unit_price")

    if not (name or "").replace(" ", "").strip():
        return error("name 不能为空", code=400)
    if not isinstance(quantity, int) or isinstance(quantity,bool) or quantity <= 0:
        return error("quantity 必须是正整数", code=400)
    if unit_price is not None and (
        not isinstance(unit_price, (int, float))
        or isinstance(unit_price, bool)
        or unit_price < 0
    ):
        return error("unit_price 不合法", code=400)

    result = _record_sale(name, quantity, unit_price)
    if not result.get("ok"):
        msg = result.get("message", "记录失败")
        code = 404 if "不存在" in msg else 400
        return error(msg, code=code)

    return success(
        data={"sale_id": result["sale_id"], "new_stock": result["new_stock"]},
        message=f"已记录销售：{name} × {quantity}",
    )
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