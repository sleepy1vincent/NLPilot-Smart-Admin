from services.tools import TOOL_FUNCTIONS
WRITE_TOOLS = {"record_sale", "record_purchase", "create_product", "update_product", "delete_product", "apply_discount"}

def handle(call: dict) -> dict:
    """根据 AI 的决策，调对应工具"""
    if not call["ok"]:
        return {"ok":False,"message":call["message"]}
    tool = call.get("tool")
    args = call.get("args") or {}
    fn = TOOL_FUNCTIONS.get(tool)
    if not fn:
        if call["is_txt"]:
            return{"ok":True,"message":call["message"],"reply":call["reply"]}
        else:
            return {"ok": False, "message": f"未知工具：{tool}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"ok": False, "message": f"执行失败：{e}"}