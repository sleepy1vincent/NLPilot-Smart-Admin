"""工具分发层

返回协议（handle）
==================
    {
      "ok":           bool,           工具执行成不成功
      "message":      str,            给用户看的一句话
      "need_confirm": bool,           需要前端弹窗确认（删除 / 打折）
      "need_clarify": bool,           需要用户补充信息
      "hint":         str,            参数错误的提示，便于模型下一轮自我纠正
      ...工具自有字段                 查询类 count/data/is_rag；变更类 affected/id/sale_id/new_stock
    }
"""
from services.tools import TOOL_FUNCTIONS
from dao import product_dao

# 这些工具要求"库里的准确商品名"
LOOKUP_TOOLS = {"record_sale", "record_purchase", "update_product", "delete_product", "apply_discount"}
# 参数里可能装商品名的键
NAME_KEYS = ("name", "product_name", "target")

#封装数据库查找的两个方式
def _lookup(raw: str):
    #准确查询
    row = product_dao.get_by_name(raw)
    if row:
        return [row]
    #模糊查询
    return product_dao.query_products(raw)
#把模型给的商品名换成准确的名字
def _resolve_args(args: dict):
    """利用rag把模型给的商品名换成库里的准确名字。
    返回 (新参数, 反问 or None)。反问不为空时**不要执行工具**。
    """

    #依次确定商品名的变量
    key = next((k for k in NAME_KEYS if args.get(k)), None)
    if not key:
        return args, None
    #把商品名出去多余空格
    raw = str(args[key]).replace(" ", "").strip()
    if not raw:
        return args, None
    #利用上面查询函数，先利用数据库的查询，查询raw相关的
    names = [c["name"] for c in _lookup(raw)]
    #原名字就有
    if raw in names:
        return args, None
    #没找到
    if not names:
        return args, f"库里没有找到「{raw}」，能说一下完整的商品名吗？"
    #只有一个相关的
    if len(names) == 1:
        new_args = dict(args)
        new_args[key] = names[0]
        return new_args, None
    #多个相关的，截取四个
    head, rest = names[0], names[1:4]
    ask = f"你是要找「{head}」吗？" + (f"库里还有：{'、'.join(rest)}" if rest else "")
    return args, ask
#核心处理函数
def handle(call: dict) -> dict:
    """根据 AI 的决策，调对应工具。

    入参是 nlu_service 的固定结构：这里只处理 kind=="tool" 的情况，
    其它情况（text / error）在 agent_service 就被拦下了，不该走到这里。
    """
    #防御：只有 tool 才是"要执行"
    if call.get("kind") != "tool":
        return {"ok": False, "message": call.get("message") or "没有可执行的工具调用"}
    #取出参数
    tool = call.get("tool")
    args = call.get("args") or {}
    fn = TOOL_FUNCTIONS.get(tool)
    #未在指定函数库里面找到调用的名字
    if not fn:
        return {"ok": False, "message": f"未知工具：{tool}"}
    #如果这个函数需要准确名字
    if tool in LOOKUP_TOOLS:
        #先把名字改好
        args, ask = _resolve_args(args)
        if ask:
            return {"ok": False, "need_clarify": True, "message": ask}
    #调用函数
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
