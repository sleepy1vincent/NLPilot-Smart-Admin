"""工具分发层：把模型的决策变成一次真实的工具调用。

职责只有两件事
--------------
    1. 商品名解析：模型说 "iphone"，换成库里的 "iPhone15"（精确 → LIKE）
    2. 分发执行：按 tool 名找到函数并调用

返回协议（handle）
------------------
成功（内容由各工具自己定义，公共字段如下）：
    {"ok": True,  "message": "...", ...工具自有字段}
        查询类通常带 count / data / is_rag
        变更类通常带 affected / id / sale_id / new_stock
        提案类带 need_confirm + action + target + message

失败：
    {"ok": False, "message": "原因"}
        商品不存在 / 参数错误 / 库存不足 / 未知工具 …
        参数错误时额外带 "hint"（可用参数列表，便于模型下一轮自我纠正）

需要用户决策（本轮**没有**执行任何写操作）：
    {"ok": False, "need_clarify": True, "message": "你是要找「iPhone15」吗？"}
        商品名对不上、有多个候选 → 反问，不猜
"""
from services.tools import TOOL_FUNCTIONS
from dao import product_dao

# 这些工具要求"库里的准确商品名"，调用前先解析
# （"哪些是写工具"这件事由 agent_service.READ_ONLY 决定，这里不再重复定义）
LOOKUP_TOOLS = {"record_sale", "record_purchase", "update_product", "delete_product", "apply_discount"}

# 参数里可能装商品名的键
NAME_KEYS = ("name", "product_name", "target")


def _lookup(raw: str):
    """按 精确 → 模糊 的顺序找商品，返回候选列表。

    这里不走 RAG：名字对齐是字符串问题，不是语义问题。
    向量只用在两处——语义查询的兜底、推荐的候选召回。
    """
    row = product_dao.get_by_name(raw)
    if row:
        return [row]
    return product_dao.query_products(raw)


def _resolve_args(args: dict):
    """利用rag把模型给的商品名换成库里的准确名字。

    返回 (新参数, 反问 or None)。反问不为空时**不要执行工具**。
    """
    key = next((k for k in NAME_KEYS if args.get(k)), None)
    if not key:
        return args, None

    raw = str(args[key]).replace(" ", "").strip()
    if not raw:
        return args, None

    names = [c["name"] for c in _lookup(raw)]

    if raw in names:              # 已经是准确名字
        return args, None
    if not names:                 # 一个都没找到
        return args, f"库里没有找到「{raw}」，能说一下完整的商品名吗？"
    if len(names) == 1:
        new_args = dict(args)
        new_args[key] = names[0]
        return new_args, None

    # 多个候选 → 反问，不猜
    head, rest = names[0], names[1:4]
    ask = f"你是要找「{head}」吗？" + (f"库里还有：{'、'.join(rest)}" if rest else "")
    return args, ask


def handle(call: dict) -> dict:
    """根据 AI 的决策，调对应工具"""
    if not call.get("ok"):
        return {"ok": False, "message": call.get("message") or "AI 未能处理请求"}
    tool = call.get("tool")
    args = call.get("args") or {}
    fn = TOOL_FUNCTIONS.get(tool)
    if not fn:
        # 模型可能编出不存在的工具名，这里不能假设 call 里一定有 is_txt
        if call.get("is_txt"):
            return {"ok": True, "message": call.get("message", "")}
        return {"ok": False, "message": f"未知工具：{tool}"}
    if tool in LOOKUP_TOOLS:
        args, ask = _resolve_args(args)
        if ask:
            return {"ok": False, "need_clarify": True, "message": ask}

    try:
        return fn(**args)
    except TypeError as e:
        return {"ok": False,
                "message": f"参数错误：{e}",
                "hint": f"{tool} 可用参数：{', '.join(_param_names(fn))}"}
    except Exception as e:
        return {"ok": False, "message": f"执行失败：{e}"}


# 返回函数的参数
def _param_names(fn):
    import inspect
    try:
        return list(inspect.signature(fn).parameters.keys())
    except (TypeError, ValueError):
        return []
