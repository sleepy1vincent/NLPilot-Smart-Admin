from flask import Blueprint, request
from services import nlu_service, product_service
from response import success, error
import dao
bp = Blueprint("chat", __name__, url_prefix="/api")


@bp.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    if not msg:
        return error("message 不能为空", code=400)

    intent = nlu_service.recognize(msg)

    result = product_service.handle(intent)

    return success(
        data={"intent": intent, "result": result},
        message=result.get("message", ""),
    )


@bp.route("/chat/confirm", methods=["POST"])
def chat_confirm():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    target = (body.get("target") or "").strip()

    if not action or not target:
        return error("缺少 action 或 target", code=400)

    if action == "delete":
        if not dao.product_dao.get_by_name(target):
            return error(f"商品 {target} 不存在", code=404)
        rows = dao.product_dao.delete_product(target)
        return success(data={"affected": rows}, message=f"已删除：{target}")

    return error(f"不支持的确认操作：{action}", code=400)