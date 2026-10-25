from flask import Blueprint, request
from services import nlu_service, product_service, rag_services, guard_service
from response import success, error
from dao import product_dao
bp = Blueprint("chat", __name__, url_prefix="/api")
@bp.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not msg:
        return error("message 不能为空", code=400)

    call = nlu_service.recognize(msg, history=history)
    decision = guard_service.inspect(call)
    if decision["executed"]:
        result = product_service.handle(call)

        # 商品名没对上 → 只是反问，什么都没执行
        if result.get("need_clarify"):
            return success(
                data={
                    "call": call,
                    "result": {**result, "kind": "none", "executed": False},
                    "reply": result.get("message", ""),
                    "executed": False,
                },
                message=result.get("message", ""),
            )

        result.setdefault("kind", "tool")
        return success(
            data={
                "call": call,
                "result": result,
                "reply": "",
                "executed": True,
            },
            message=result.get("message", ""),
        )
    reply = call.get("message") or call.get("reply") or ""
    if not reply:
        reply = "AI 未能处理这次请求，请重试。"
    return success(
        data={
            "call": call,
            "result": {"ok": False, "kind": "none", "executed": False},
            "reply": reply,
            "executed": False,
        },
        message=reply,
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
        if rows == 0:
            return error(f"{target} 删除失败（可能已被删除）", code=409)
        try:
            rag_services.delete_products([product["id"]])
        except Exception as e:
            print(f"[RAG] 删除同步失败 id={product['id']}: {e}")
        return success(data={"affected": rows}, message=f"已删除：{target}")
    if action=="discount" and isinstance(data,int|float) and not isinstance(data,bool):
        rows=product_dao.update_product(target,{"price":data})
        if rows == 0:
            return success(data={"affected": 0},
                           message=f"{target} 的价格已经是 {data}，未做修改")
        return success(data={"affected":rows},message=f"已更改{target}价格为{data}")
    return error(f"不支持的确认操作：{action}", code=400)