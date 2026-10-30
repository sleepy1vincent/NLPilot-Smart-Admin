"""Agent 执行层
分装Agent模型的逻辑

对外只有两个函数
----------------
    run_once(msg, history)  单步：模型决策一次，执行一次，结束
    run_loop(msg, history)  多步：决策 → 执行 → 看观察 → 再决策……最多 MAX_STEPS 步
协议
--------
{
  "call":     {...},      # 最后一次模型决策（无决策时为 {}）
  "result":   {...},      # 事实通道：只来自工具返回值，模型改不了
  "reply":    "...",      # 对话通道：模型的话（可能为空）
  "executed": 0 | 1 | 2,  # 本轮真正执行成功了几次工具
  "trace":    [ {...} ],  # 每步记录；单步也有一条，便于前端显示"经过几步"
}

两个通道的填充规则
----------------------------------------------
    executed == 0
        result = {"ok": False, "kind": "none"}
        reply  = 模型的话（前端标「未执行数据库操作」）

    单步 && executed >= 1
        result = 工具返回值
        reply  = ""            ← 有事实就不让模型复述

    多步 && executed >= 1（且是模型主动收尾）
        result = 最后一次工具返回值
        reply  = 模型的总结     ← 多步的答案就在这里

    工具执行结果里出现 need_confirm / need_clarify
        立刻结束（不继续循环），把提案/反问交回前端；
        这类情况 executed 记 0 —— 因为"提案"不等于"执行"。
"""
import json

from services import nlu_service, product_service, guard_service, reply_templates

# 多步循环上限
MAX_STEPS = 3

# 只读工具
READ_ONLY = {
    "query_products",
    "recommend_products",
    "query_sales",
    "sales_report",
    "query_purchases",
}
#封装对话结果
def _none_result() -> dict:
    """没有执行任何工具时的"事实通道"内容。"""
    return {"ok": False, "kind": "none", "executed": False}
#判断ai是否是文字的需要确认或者拒绝执行
def _dialog_text(call: dict):
    tool = call.get("tool")
    args = call.get("args") or {}
    value = args.get("field") or args.get("reason") or ""
    if tool == "clarify":
        return reply_templates.render_clarify(value, args.get("candidates", ""))
    if tool == "refuse":
        return reply_templates.render_refuse(value)
    return None
#兜底函数，没用工具时候的返回
def _no_tool_text(call: dict) -> str:
    if call.get("ok") is False:
        return call.get("message") or reply_templates.FALLBACK
    return reply_templates.FALLBACK
#打包函数——封装（llm的决策、工具结果、llm的回复、执行过的工具、前几轮的数据）
def _pack(call, result, reply, executed, trace, results=None) -> dict:
    return {
        "call": call or {},
        "result": result or _none_result(),
        "results": results or [],
        "reply": reply,
        "executed": executed,
        "trace": trace,
    }
#压缩上文总结(收到的结果、最大容量、最大字符数）
def _shrink(result: dict, max_items: int = 3, max_chars: int = 600) -> str:
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
    result = product_service.handle(call)
    #记录该步操作，返回（只留调试真正会看的字段）
    trace = [{"step": 1, "tool": tool, "args": call.get("args") or {},
              "ok": bool(result.get("ok"))}]
    #如果工具调取中需要确认选项
    if result.get("need_confirm") or result.get("need_clarify"):
        return _pack(call, {**result, "kind": "none", "executed": False},
                     result.get("message", ""), 0, trace)
    result.setdefault("kind", "tool")
    #记录已经执行过一遍
    executed = 1 if result.get("ok") else 0
    results = ([{"step": 1, "tool": tool, "args": call.get("args") or {},
                 "result": result}] if executed else [])
    return _pack(call, result, "", executed, trace, results)
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
    trace, seen = [], set()
    executed = 0
    #记录是否已经进行一次写操作了
    write_done = False
    #记录上次内容
    last_call, last_result = {}, None
    #每一步的执行结果
    results = []

    for step in range(max_steps):
        call = nlu_service.recognize(messages, max_retries=2, retry_text=True)
        decision = guard_service.inspect(call)

        #模型决定直接说话
        if not decision["executed"]:
            # executed == 0 时不许展示模型文字（那可能是编的）；有执行过才允许当"总结"
            reply = "" if executed else _no_tool_text(call)
            # last_call 只记"工具决策"，这里不覆盖它
            return _pack(last_call, last_result, reply, executed, trace, results)

        last_call = call
        tool, args = decision["tool"], call.get("args") or {}

        #clarify / refuse —— 模板渲染后立刻结束（不执行工具）
        dialog = _dialog_text(call)
        if dialog is not None:
            trace.append({"step": step + 1, "tool": tool, "args": args, "ok": False})
            return _pack(call, _none_result(), dialog, executed, trace, results)

        #同名同参重复调用
        key = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if key in seen:
            trace.append({"step": step + 1, "tool": tool, "skipped": "重复调用"})
            break
        seen.add(key)  #记录调取记录

        #本轮已经写过一次，再写就掐掉（防一次请求连写多笔）
        if tool not in READ_ONLY and write_done:
            trace.append({"step": step + 1, "tool": tool,
                          "skipped": "本轮已执行过写操作，不再重复写"})
            break
        #剩下的正常去product
        result = product_service.handle(call)
        last_result = result
        ok = bool(result.get("ok"))
        if ok:
            executed += 1 #执行次数+1
            results.append({"step": step + 1, "tool": tool,
                            "args": args, "result": result})
        trace.append({"step": step + 1, "tool": tool, "args": args, "ok": ok})

        #提案或反问，交给前端，不继续
        if result.get("need_confirm") or result.get("need_clarify"):
            return _pack(call, {**result, "kind": "none", "executed": False},
                         result.get("message", ""), executed, trace, results)
        #进行一次写操作了
        if tool not in READ_ONLY and ok:
            write_done = True

        # 观察回灌，记录这次对话
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
    return _pack(last_call, result, "", executed, trace, results)
