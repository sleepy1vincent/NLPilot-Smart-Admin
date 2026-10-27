"""Agent 执行层：把「模型决策 → 执行工具 → 组织回复」固化成一个契约。

对外只有两个函数
----------------
    run_once(msg, history)  单步：模型决策一次，执行一次，结束
    run_loop(msg, history)  多步：决策 → 执行 → 看观察 → 再决策……最多 MAX_STEPS 步

两者返回结构完全一致（见下），所以路由和前端只需要认一种格式，
切换单步/多步不会改变调用方。


返回协议
--------
{
  "call":     {...},      # 最后一次模型决策（无决策时为 {}）
  "result":   {...},      # 事实通道：只来自工具返回值，模型改不了
  "reply":    "...",      # 对话通道：模型的话（可能为空）
  "executed": 0 | 1 | 2,  # 本轮真正执行成功了几次工具
  "trace":    [ {...} ],  # 每步记录；单步也有一条，便于前端显示"经过几步"
}

两个通道的填充规则（这条最容易记错，务必保持）
----------------------------------------------
    executed == 0
        result = {"ok": False, "kind": "none"}
        reply  = 模型的话（前端标「未执行数据库操作」）

    单步 && executed >= 1
        result = 工具返回值
        reply  = ""            ← 有事实就不让模型复述（它常说错数字）

    多步 && executed >= 1（且是模型主动收尾）
        result = 最后一次工具返回值
        reply  = 模型的总结     ← 多步的答案就在这里

工具执行结果里出现 need_confirm / need_clarify
    立刻结束（不继续循环），把提案/反问交回前端；
    这类情况 executed 记 0 —— 因为"提案"不等于"执行"。
"""
import json

from services import nlu_service, product_service, guard_service

# 多步循环上限
MAX_STEPS = 3

# 只读工具：失败可以重试、可以连续调用
# 写工具不在这个集合里 —— 它们"成功即结束循环"，避免一次请求连写多笔
READ_ONLY = {
    "query_products",
    "recommend_products",
    "query_sales",
    "sales_report",
    "query_purchases",
}


def _none_result() -> dict:
    """没有执行任何工具时的"事实通道"内容。"""
    return {"ok": False, "kind": "none", "executed": False}


#打包函数——封装（llm的决策、工具结果、llm的回复、执行过的工具、第几轮）
def _pack(call, result, reply, executed, trace) -> dict:
    return {
        "call": call or {},
        "result": result or _none_result(),
        "reply": reply,
        "executed": executed,
        "trace": trace,
    }

#压缩上文总结(收到的结果、
def _shrink(result: dict, max_items: int = 3, max_chars: int = 600) -> str:
    """把工具返回值压成"模型够用、上下文撑得住"的观察。

    27 个商品的全量 JSON 约 4000 字符，三步就爆上下文 —— 这是多步循环最常见的坑。
    """
    if not isinstance(result, dict):
        return str(result)[:max_chars]

    out = {}
    for k, v in result.items():
        if isinstance(v, list):
            out[k] = v[:max_items]
            if len(v) > max_items:
                out["_note"] = f"共 {len(v)} 条，只显示前 {max_items} 条"
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v

    s = json.dumps(out, ensure_ascii=False, default=str)
    return s if len(s) <= max_chars else s[:max_chars] + "…（已截断）"


def run_once(msg: str, history: list = None) -> dict:
    """单步：模型决策一次 → 执行一次 → 结束。
    这就是多步循环的 max_steps=1 特例，只是不产生"观察回灌"。
    """
    call = nlu_service.recognize(msg, history=history)
    if not guard_service.inspect(call)["executed"]:
        reply = call.get("message") or "AI 未能处理这次请求，请重试。"
        return _pack(call, _none_result(), reply, 0, [])
    result = product_service.handle(call)
    trace = [{"step": 1, "tool": call.get("tool"), "args": call.get("args") or {},
              "ok": bool(result.get("ok")), "count": result.get("count")}]
    if result.get("need_confirm") or result.get("need_clarify"):
        return _pack(call, {**result, "kind": "none", "executed": False},
                     result.get("message", ""), 0, trace)
    result.setdefault("kind", "tool")
    executed = 1 if result.get("ok") else 0
    return _pack(call, result, "", executed, trace)


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
    messages = nlu_service.build_messages(msg, history)
    trace, seen = [], set()
    executed = 0
    write_done = False          # 本轮是否已经成功写过一次
    last_call, last_result = {}, None

    for step in range(max_steps):
        # 循环内每步最多两次调用（第二次用于：空响应补提示、或把"该调工具却回了文字"掰回来）
        call = nlu_service.recognize(messages, max_retries=2, retry_text=True)

        # 出口 1：模型决定直接说话（多步的"总结"通常在这里）
        if not call.get("tool"):
            reply = call.get("message") or ""
            if executed == 0 and not reply:
                reply = "AI 未能处理这次请求，请重试。"
            # last_call 只记"工具决策"，这里不覆盖它
            return _pack(last_call, last_result, reply, executed, trace)

        last_call = call
        tool, args = call["tool"], call.get("args") or {}

        # 出口 2：同名同参重复调用
        key = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if key in seen:
            trace.append({"step": step + 1, "tool": tool, "skipped": "重复调用"})
            break
        seen.add(key)

        # 出口 3：本轮已经写过一次，再写就掐掉（防一次请求连写多笔）
        # 注意：写完之后**不结束循环**——用户可能一次要求两件事
        #（"创建X，再推荐Y"），只写一次、但可以接着做只读的事。
        if tool not in READ_ONLY and write_done:
            trace.append({"step": step + 1, "tool": tool,
                          "skipped": "本轮已执行过写操作，不再重复写"})
            break

        result = product_service.handle(call)
        last_result = result
        ok = bool(result.get("ok"))
        if ok:
            executed += 1
        trace.append({"step": step + 1, "tool": tool, "args": args,
                      "ok": ok, "count": result.get("count")})

        # 出口 4 / 5：提案或反问，交给前端，不继续
        if result.get("need_confirm") or result.get("need_clarify"):
            return _pack(call, {**result, "kind": "none", "executed": False},
                         result.get("message", ""), executed, trace)

        if tool not in READ_ONLY and ok:
            write_done = True

        # 观察回灌（必须压缩）
        messages.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": tool, "arguments": args}}],
        })
        messages.append({
            "role": "tool", "tool_name": tool, "content": _shrink(result),
        })

    # 出口 5 / 6 收口：没有模型的总结，就用最后一次工具结果当事实
    result = last_result or _none_result()
    result.setdefault("kind", "tool" if executed else "none")
    return _pack(last_call, result, "", executed, trace)
