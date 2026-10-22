from flask import Blueprint, request
from services import nlu_service, product_service, rag_services
from response import success, error
from dao import product_dao
bp = Blueprint("chat", __name__, url_prefix="/api")
SAFE_HINTS = ["你好", "谢谢", "是什么", "多少钱", "几个", "有哪些", "查询", "查一下", "看看", "情况", "统计", "记录吗"]
@bp.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not msg:
        return error("message 不能为空", code=400)

    call = nlu_service.recognize(msg, history=history)
    result = product_service.handle(call)
    if call.get("is_txt") and not call.get("tool"):
        if any(h in msg for h in SAFE_HINTS):
            return success(data={"call": call, "result": {
                "ok": True, "message": call.get("message", ""),
            }}, message=call.get("message", ""))
            # 其余一律明确告知"未执行"
        return success(data={"call": call, "result": {
            "ok": False,
            "message": "我没能理解你的操作意图，请换一种说法重试（未执行任何操作）",
        }}, message="未能执行")
    return success(
        data={"call": call, "result": result},
        message=result.get("message", ""),
    )
@bp.route("/chat/confirm", methods=["POST"])
def chat_confirm():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    target = (body.get("target") or "").strip()
    data=body.get("data")

    if not action or not target:
        return error("缺少 action 或 target", code=400)

    if action == "delete":
        product=product_dao.get_by_name(target)
        if not product:
            return error(f"商品 {target} 不存在", code=404)
        rows = product_dao.delete_product(target)
        try:
            rag_services.delete_products([product["id"]])
        except Exception as e:
            print(f"[RAG] 删除同步失败 id={product['id']}: {e}")
        return success(data={"affected": rows}, message=f"已删除：{target}")
    if action=="discount" and isinstance(data,int|float) and not isinstance(data,bool):
        rows=product_dao.update_product(target,{"price":data})
        return success(data={"affected":rows},message=f"已更改{target}价格为{data}")
    return error(f"不支持的确认操作：{action}", code=400)