from services.tools import TOOL_FUNCTIONS


def handle(call: dict) -> dict:
    """根据 AI 的决策，调对应工具"""
    if "error" in call:
        return {"ok": False, "message": f"AI 调用失败：{call['error']}"}
    if "reply" in call:
        return {"ok": True, "message": call["reply"]}

    tool = call.get("tool")
    args = call.get("args") or {}

    fn = TOOL_FUNCTIONS.get(tool)
    if not fn:
        return {"ok": False, "message": f"未知工具：{tool}"}

    try:
        return fn(**args)
    except Exception as e:
        return {"ok": False, "message": f"执行失败：{e}"}