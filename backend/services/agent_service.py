"""Agent 执行层

对外只有两个函数
----------------
    run_once(msg, history)  单步
    run_loop(msg, history)  多步

返回协议（run_once / run_loop，两者完全一致）
============================================
    {
      "call":     dict,          工具决策，具体内容由对话层决定
      "result":   dict,          最后一次工具返回值；没执行为 {"ok":False,"kind":"none"}
      "steps":    list,          每一步的记录
      "reply":    str,           ai的实际回复（胡说八道/实际总结）
      "executed": int,           真正执行成功的工具次数
    }

    steps 每条三选一：
        {"step": int, "tool": str, "args": dict, "ok": True,  "result": dict}   执行成功
        {"step": int, "tool": str, "args": dict, "ok": False}                   执行失败
        {"step": int, "tool": str, "args": dict, "skipped": str}                被拦下（重复调用 / 写预算）
"""
import json

from services import nlu_service, product_service, guard_service, reply_templates
from dao import sales_dao

# 多步循环上限
MAX_STEPS = 5

# 只读工具
READ_ONLY = {
    "query_products",
    "recommend_products",
    "discount_candidates",
    "query_sales",
    "sales_report",
    "query_purchases",
}
#封装对话结果
def _none_result() -> dict:
    """没有执行任何工具时的"事实通道"内容。"""
    return {"ok": False, "kind": "none", "executed": False}
#单商品查询补上日均销量和可售天数：换算是确定性的，不该让模型算
def _enrich(result: dict) -> dict:
    data = result.get("data")
    if not isinstance(data, list) or len(data) != 1:
        return result
    row = data[0]
    if not isinstance(row, dict) or "stock" not in row or not row.get("name"):
        return result
    sold = sales_dao.total_sold(product_name=row["name"], days=30)
    daily = round(sold / 30, 2)
    row["daily_sold"] = daily
    row["days_left"] = round(row["stock"] / daily) if daily > 0 else None
    return result
#判断ai是否是文字的需要确认或者拒绝执行
def _dialog_text(call: dict):
    tool = call.get("tool")
    args = call.get("args") or {}
    if tool == "clarify":
        return reply_templates.render_clarify(args.get("slots", ""), args.get("candidates", ""))
    if tool == "refuse":
        return reply_templates.render_refuse(args.get("reason", ""))
    return None
#兜底函数，没用工具时候的返回
def _no_tool_text(call: dict) -> str:
    if call.get("kind") == "error":
        return call.get("message") or reply_templates.FALLBACK
    return reply_templates.FALLBACK
#打包函数——封装（llm的决策、最后一次结果、llm的回复、执行次数、每步记录）
def _pack(call, result, reply, executed, steps=None) -> dict:
    """统一返回结构。

    只有一条 `steps` 记录每一步；不再有 trace/results 两条平行数组
    （它们前三个字段完全重复，只是一个记 ok、一个记 result）。
    """
    return {
        "call": call or {},
        "result": result or _none_result(),
        "reply": reply,
        "executed": executed,
        "steps": steps or [],
    }
#压缩上文总结(收到的结果、最大容量、最大字符数）
def _shrink(result: dict, max_items: int = 10, max_chars: int = 2000) -> str:
    #如果不是字典类型，则直接说明是文本返回，直接返回
    if not isinstance(result, dict):
        return str(result)[:max_chars]
    out = {}
    for k, v in result.items():
        #如果是多条，则截取部分
        if isinstance(v, list):
            out[k] = v[:max_items]
            if len(v) > max_items:
                out["_note"] = f"共 {len(v)} 条，只显示前 {max_items} 条"
        #如果是一条，则截取一般
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    #将字典类型转为字符串
    s = json.dumps(out, ensure_ascii=False, default=str)
    return s if len(s) <= max_chars else s[:max_chars] + "…（已截断）"
def run_once(msg: str, history: list = None) -> dict:
    """单步：模型决策一次→执行一次→结束。
    这就是多步循环的 max_steps=1 特例，只是不产生"观察回灌"。
    """
    #发送给模型端信息
    call = nlu_service.recognize(msg, history=history)
    #输出内容经过幻觉守卫处理，主要用来区分模型是否真的调用了工具
    decision = guard_service.inspect(call)
    tool = decision["tool"]
    #ai明确拒绝或者反问
    dialog = _dialog_text(call)
    if dialog is not None:
        return _pack(call, _none_result(), dialog, 0,
                     [{"step": 1, "tool": tool, "args": call.get("args") or {},
                       "ok": False}])
    #并没有任何调用
    if not decision["executed"]:
        return _pack(call, _none_result(), _no_tool_text(call), 0, [])
    #没用明显则交由工具端
    result = _enrich(product_service.handle(call))
    step = {"step": 1, "tool": tool, "args": call.get("args") or {},
            "ok": bool(result.get("ok"))}
    #如果工具调取中需要确认选项
    if result.get("need_confirm") or result.get("need_clarify"):
        return _pack(call, {**result, "kind": "none", "executed": False},
                     result.get("message", ""), 0, [step])
    result.setdefault("kind", "tool")
    #记录已经执行过一遍
    executed = 1 if result.get("ok") else 0
    if executed:
        step["result"] = result
    return _pack(call, result, "", executed, [step])
#多步函数
def run_loop(msg: str, history: list = None, max_steps: int = MAX_STEPS) -> dict:
    """多步：决策 → 执行 → 观察回灌 → 再决策……直到模型收尾或触顶。
六个出口：
      1. 模型不调工具       → 文字作为总结
      2. 同名同参重复       → 停（防原地打转）
      3. 本轮已写过一次      → 再要写就停（防一次请求连写多笔）
      4. need_confirm       → 立刻交前端弹窗
      5. need_clarify       → 立刻反问用户
      6. 步数用尽           → 用最后一次工具结果收口

注意：写操作成功 **不会** 结束循环（否则"创建 X，再推荐 Y"只能做一半）；
改用"写预算"——整轮最多成功写一次，之后的写请求被掐断，只读的照常执行。
    """
    #压缩上文
    messages = nlu_service.build_messages(msg, history)
    steps, seen = [], set()
    executed = 0
    #记录是否已经进行一次写操作了
    write_done = False
    #记录上次内容
    last_call, last_result = {}, None

    for step in range(max_steps):
        call = nlu_service.recognize(messages, max_retries=2, retry_text=True)
        decision = guard_service.inspect(call)

        #模型决定直接说话
        if not decision["executed"]:
            # executed == 0 时不许展示模型文字（那可能是编的）；有执行过才允许当"总结"
            if executed:
                reply=(call.get("message") or "").strip()[:300]
            else:
                reply=_no_tool_text(call)
            return _pack(last_call, last_result, reply, executed, steps)

        last_call = call
        tool, args = decision["tool"], call.get("args") or {}

        #大模型要求clarify / refuse
        dialog = _dialog_text(call)
        if dialog is not None:
            steps.append({"step": step + 1, "tool": tool, "args": args, "ok": False})
            return _pack(call, _none_result(), dialog, executed, steps)

        #同名同参重复调用
        key = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if key in seen:
            steps.append({"step": step + 1, "tool": tool, "args": args,
                          "skipped": "重复调用"})
            break
        seen.add(key)  #记录调取记录

        #本轮已经写过一次，再写就掐掉
        if tool not in READ_ONLY and write_done:
            steps.append({"step": step + 1, "tool": tool, "args": args,
                          "skipped": "本轮已执行过写操作，不再重复写"})
            break
        #剩下的正常去product
        result = _enrich(product_service.handle(call))
        last_result = result
        ok = bool(result.get("ok"))
        #一步一条记录
        entry = {"step": step + 1, "tool": tool, "args": args, "ok": ok}
        if ok:
            executed += 1 #执行次数+1
            entry["result"] = result
        steps.append(entry)

        #工具提问或反问，交给前端，不继续
        if result.get("need_confirm") or result.get("need_clarify"):
            return _pack(call, {**result, "kind": "none", "executed": False},
                         result.get("message", ""), executed, steps)
        #进行一次写操作了
        if tool not in READ_ONLY and ok:
            write_done = True

        # 观察回灌：assistant（我调了什么）+ tool（环境返回了什么）
        messages.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": tool, "arguments": args}}],
        })
        messages.append({
            "role": "tool", "tool_name": tool, "content": _shrink(result),
        })

    # 收口：没有模型的总结，就用最后一次工具结果当事实
    result = last_result or _none_result() 
    result.setdefault("kind", "tool" if executed else "none")
    return _pack(last_call, result, "", executed, steps)
