"""对话接口层：只做 HTTP 的事，业务全在 services/agent_service.py。

返回协议（POST /api/chat）
-------------------------
HTTP 恒为 200（业务结果放在 data 里）：
{
  "code": 200, "message": "...",
  "data": {
      "call":     {...},        # 最后一次模型决策
      "result":   {...},        # 事实通道：只来自工具
      "reply":    "...",        # 对话通道：模型的话
      "executed": 0 | 1 | 2,    # 真正执行成功了几次
      "trace":    [ {...} ]     # 每步记录
  }
}

POST /api/chat/confirm
----------------------
成功: {"code":200,"data":{"affected":N},"message":"已删除：X"}
失败: HTTP 400/404/409 + {"code":同状态码,"message":"原因","data":null}
"""
from flask import Blueprint, request

from config import Config
from services import agent_service, rag_services
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

    # 单步 / 多步：两个实现，同一种返回结构
    if Config.CHAT_LOOP:
        payload = agent_service.run_loop(msg, history)
    else:
        payload = agent_service.run_once(msg, history)

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
