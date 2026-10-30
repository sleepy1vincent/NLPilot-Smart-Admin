from flask import Blueprint, request
from pymysql.err import IntegrityError
from dao import product_dao
from response import success, error
from services.tools import create_product as _create_product
bp = Blueprint("product", __name__, url_prefix="/api")


# ============ 查询列表 ============
@bp.route("/products", methods=["GET"])
def get_products():
    """查询商品，支持 ?name=xxx 模糊查询"""
    name = request.args.get("name")
    rows = product_dao.query_products(name)
    return success(data=rows, message=f"共 {len(rows)} 条")


# ============ 新增 ============
@bp.route("/products", methods=["POST"])
def add_product():
    """新增商品，body: {name, price, stock}"""
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    price = body.get("price")
    stock = body.get("stock")
    name = (name or "").replace(" ", "").strip()
    # 参数校验
    if not name:
        return error("name 不能为空", code=400)
    if not isinstance(price, (int, float)) or isinstance(price,bool) or price < 0:
        return error("price 必须是非负数", code=400)
    if not isinstance(stock, int) or isinstance(stock,bool) or stock < 0:
        return error("stock 必须是非负整数", code=400)

    # 重名检查
    if product_dao.get_by_name(name):
        return error(f"商品 {name} 已存在", code=409)

    try:
        result = _create_product(name, price, stock)
        if not result.get("ok"):
            msg = result.get("message", "新增失败")
            return error(msg, code=409 if "已存在" in msg else 400)
        return success(data={"id": result["id"]}, message="新增成功")
    except IntegrityError as e:
        if e.args[0] == 1062:
            return error(f"商品 {name} 已存在", code=409)
        return error(f"数据库错误：{e}", code=500)
    except Exception as e:
        return error(f"新增失败：{e}", code=500)


# ============ 修改 ============
@bp.route("/products/<name>", methods=["PUT"])
def update_product(name):
    body = request.get_json(silent=True) or {}
    name = (name or "").replace(" ", "").strip()
    if not product_dao.get_by_name(name):
        return error(f"商品 {name} 不存在", code=404)

    allowed = ("price", "stock")
    fields = {}
    for k in allowed:
        if k in body:
            v = body[k]
            if k == "price":
                if not isinstance(v, (int, float)) or isinstance(v,bool) or v < 0:
                    return error("price 必须是非负数", code=400)
                fields[k] = v
            elif k == "stock":
                if not isinstance(v, int) or isinstance(v,bool) or v < 0:
                    return error("stock 必须是非负整数", code=400)
                fields[k] = v
    if not fields:
        return error("没有可修改的字段（只能改 price / stock）", code=400)
    try:
        rows = product_dao.update_product(name, fields)
        return success(data={"affected": rows}, message=f"修改成功")
    except Exception as e:
        return error(f"修改失败：{e}", code=500)


@bp.route("/products/<name>", methods=["DELETE"])
def delete_product(name):
    """删除商品"""
    name = (name or "").replace(" ", "").strip()
    if not product_dao.get_by_name(name):
        return error(f"商品 {name} 不存在", code=404)

    try:
        rows = product_dao.delete_product(name)
        return success(data={"affected": rows}, message=f"删除成功：{name}")
    except Exception as e:
        return error(f"删除失败：{e}", code=500)