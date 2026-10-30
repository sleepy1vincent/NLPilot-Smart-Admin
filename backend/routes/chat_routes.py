"""对话接口层：只做 HTTP 的事，业务全在 services/agent_service.py。

返回协议（POST /api/chat）
-------------------------
请求：{"message": "...", "conversation_id": 12}      conversation_id 可省略（省略则新建）
响应（HTTP 恒 200）：
{
  "code": 200, "message": "...",
  "data": {
      "conversation_id": 12,      # 新增：前端存下来，下次带上
      "call":     {...},          # 最后一次模型决策
      "result":   {...},          # 事实通道：只来自工具
      "reply":    "...",          # 对话通道：模板文案 / 多步总结（可为空）
      "executed": 0 | 1 | 2,      # 真正执行成功了几次
      "trace":    [ {...} ]       # 每步记录
  }
}

会话接口
--------
GET    /api/conversations          → [{"id","title","count","last_update"}]
GET    /api/conversations/<id>     → {"id","last_update","messages":[{"role","content","at"}]}
DELETE /api/conversations/<id>     → {"affected": N}

POST /api/chat/confirm
----------------------
成功: {"code":200,"data":{"affected":N},"message":"已删除：X"}
失败: HTTP 400/404/409 + {"code":同状态码,"message":"原因","data":null}
"""
from flask import Blueprint, request

from config import Config
from services import agent_service, rag_services
from response import success, error
from dao import product_dao, conversation_dao

bp = Blueprint("chat", __name__, url_prefix="/api")


@bp.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    conv_id = body.get("conversation_id")
    if not msg:
        return error("message 不能为空", code=400)

    try:
        conv_id = int(conv_id) if conv_id else conversation_dao.create()
    except (TypeError, ValueError):
        return error("conversation_id 不合法", code=400)
    #获取历史
    history = conversation_dao.history(conv_id, turns=6)
    if Config.CHAT_LOOP:
        payload = agent_service.run_loop(msg, history)
    else:
        payload = agent_service.run_once(msg, history)
    #读取模型回复
    shown = payload.get("reply") or payload["result"].get("message") or ""
    #如果没有回复则加上默认值
    if not shown and payload.get("executed"):
        shown = "（已执行）"
    try:
        conversation_dao.add_message(conv_id, "user", msg)
        if shown:
            conversation_dao.add_message(conv_id, "ai", shown)
    except Exception as e:
        print(f"[会话] 记录失败 conv={conv_id}: {e}")

    payload["conversation_id"] = conv_id
    return success(data=payload, message=shown or "（无回复）")


@bp.route("/conversations", methods=["GET"])
def list_conversations():
    return success(data=conversation_dao.list_conversations(), message="ok")


@bp.route("/conversations/<int:conv_id>", methods=["GET"])
def get_conversation(conv_id):
    data = conversation_dao.get_conversation(conv_id)
    if not data:
        return error("会话不存在", code=404)
    return success(data=data, message="ok")


@bp.route("/conversations/<int:conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    rows = conversation_dao.delete(conv_id)
    if rows == 0:
        return error("会话不存在", code=404)
    return success(data={"affected": rows}, message="已删除对话")

    message = payload.get("reply") or payload["result"].get("message", "")
    return success(data=payload, message=message)


@bp.route("/chat/confirm", methods=["POST"])
def chat_confirm():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    target = (body.get("target") or "").strip()
    data = body.get("data")

    if not action or not target:
        return error("缺少 action 或 target", code=400)

    if action == "delete":
        product = product_dao.get_by_name(target)
        if not product:
            return error(f"商品 {target} 不存在", code=404)
        rows = product_dao.delete_product(target)
        # 影响 0 行 = 实际没删掉，不能报"已删除"
        if rows == 0:
            return error(f"{target} 删除失败（可能已被删除）", code=409)
        try:
            rag_services.delete_products([product["id"]])
        except Exception as e:
            print(f"[RAG] 删除同步失败 id={product['id']}: {e}")
        return success(data={"affected": rows}, message=f"已删除：{target}")

    if action == "discount" and isinstance(data, int | float) and not isinstance(data, bool):
        rows = product_dao.update_product(target, {"price": data})
        # 影响 0 行 = 价格本来就是这个值，不能报"已更改"
        if rows == 0:
            return success(data={"affected": 0},
                           message=f"{target} 的价格已经是 {data}，未做修改")
        return success(data={"affected": rows}, message=f"已更改{target}价格为{data}")

    return error(f"不支持的确认操作：{action}", code=400)
