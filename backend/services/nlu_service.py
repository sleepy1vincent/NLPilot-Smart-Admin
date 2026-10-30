"""意图识别层

返回协议（recognize）
---------------------
    {"ok": True,  "tool": "query_products", "args": {...}}
        模型选了一个工具。

    {"ok": True,  "tool": "...", "args": {...}, "recovered": True}
        同上，但是这个调用是从"泄漏成文本的 tool_call"里解析回来的（qwen2.5 偶发）。

    {"ok": True,  "is_txt": True, "message": "..."}
        模型只回了文字（闲聊 / 反问 / 拒绝）。

    {"ok": False, "message": "..."}
        调用失败（模型异常 / 返回空 / 泄漏且无法解析）。
        此时 message 已是"能给用户看"的话术，调用方直接展示即可。

上游（agent_service）只看两个字段：
    有 tool → 交给 product_service.handle 执行
    无 tool → message 走"对话通道"

注 1：v3.0 曾同时返回 message 和 reply，但两者在成功分支是同一个变量，
      失败分支的 reply 也从没被读过 —— 已删除，只保留 message。
注 2：ollama 有个已知问题——模型偶尔把 tool_call 生成成解析不了的形式，
      结果是 content 和 tool_calls 同时为空（实测"有哪些耳机"必现，6 个 seed 全空）。
      对策是给最后一条 user 消息补一句"（请用工具查询）"再试，实测能恢复。
"""
import json
import re

import ollama

from config import Config
from prompts.system_prompt import SYSTEM_PROMPT
from services.tools import TOOLS_FOR_AI, TOOL_FUNCTIONS
#补充内容，防止多次无用功
_NUDGE = "（业务操作和查询必须调用工具；只有纯闲聊才直接回答）"
#建立输入文本（记忆化）
def build_messages(user_input: str, history: list = None) -> list:
    """拼出初始 messages：system + 最近几轮历史 + 本轮用户输入。

    多步循环会在返回的列表上继续 append（assistant 的 tool_calls + tool 的观察），
    所以调用方要拿它当可变列表用。
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_input})
    return messages
#防止多次无用功，给上一次的内容添点
def _nudged(messages: list) -> list:
    """复制一份 messages，并在最后一条 user 消息末尾补上 _NUDGE。

    不修改原列表（循环里的 messages 是累积的，不能污染）。
    已经补过就不再补，避免重复拼接。
    """
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            text = m.get("content") or ""
            if _NUDGE not in text:
                m["content"] = text + _NUDGE
            break
    return out
#防止模型泄露too_call
def _is_tool_leak(content: str) -> bool:
    if not content:
        return False
    markers = ["<tool_call>", "</tool_call>", '{"name":', '"arguments"', "leton"]
    if any(m in content for m in markers):
        return True
    return bool(_LEAK_PY.search(content) or _LEAK_FN_JSON.search(content))
_LEAK_CALL = re.compile(
    r'\{\s*"name"\s*:\s*"([A-Za-z_]\w*)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
    re.S,
)
_LEAK_PY = re.compile(
    r'\b([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*=\s*["\']?([^"\'),]*?)["\']?\s*\)'
)
_LEAK_FN_JSON = re.compile(
    r'\b([A-Za-z_]\w*)\s*\(\s*(\{.*?\})\s*\)',
    re.S,
)
_LEAK_CALLARGS = re.compile(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)")
_KWARG = re.compile(r"(\w+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^,]+)")

#还原泄露文本
def _coerce(v: str):
    v = (v or "").strip().strip('"').strip("'")
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v.lower() in ("none", "null"):
        return None
    return v
def _recover_py_call(content: str):
    """从 `x({"k": "v"})` / `x(k=v)` / `x(k=v, k2=v2)` 这类文本里恢复调用。"""
    content = content or ""

    for m in _LEAK_FN_JSON.finditer(content):
        name, raw = m.group(1), m.group(2)
        if name not in TOOL_FUNCTIONS:
            continue
        try:
            args = json.loads(raw)
        except Exception:
            continue
        if isinstance(args, dict):
            return {"name": name, "args": args}

    for m in _LEAK_CALLARGS.finditer(content):
        name, inner = m.group(1), m.group(2)
        if name not in TOOL_FUNCTIONS or "=" not in inner:
            continue
        args = {k: _coerce(v) for k, v in _KWARG.findall(inner)}
        if args:
            return {"name": name, "args": args}
    return None
#从泄露中捞出tool_call
def _recover_tool_call(content: str):
    """从泄漏文本里把 tool_call 捞回来。

    qwen2.5 有时把 tool_call 当普通文本吐出来（`</tool_call>` 前后夹着完整 JSON）。
    三次重试往往吐出一模一样的内容，重试没有意义——但那串 JSON 是完整的，
    解析出来就能当正常工具调用用。
    """
    if not content:
        return None
    m = _LEAK_CALL.search(content)
    if not m:
        return _recover_py_call(content)
    name, raw_args = m.group(1), m.group(2)
    if name not in TOOL_FUNCTIONS:
        return None
    try:
        args = json.loads(raw_args)
    except Exception:
        return None
    return {"name": name, "args": args if isinstance(args, dict) else {}}

#核心做决策函数
def recognize(user_input, history: list = None, max_retries: int = 3,
              retry_text: bool = False) -> dict:
    """让模型做一次决策。
    参数
      user_input : 字符串（内部拼 messages）或已拼好的 messages 列表（多步循环用）
      history    : 仅当 user_input 是字符串时生效
      max_retries: 单步默认 3 次；多步循环里每步建议传 2
      retry_text : 收到"纯文字回复"时要不要再试一次。
                   · 单步：False —— 闲聊第一句就答得很好，重试反而逼它去查商品
                   · 循环：True  —— 用户常说"再把它打八折"这种，第一步回了文字
                                    就会漏掉第二步的动作
    """
    #判断参数类型，base存放基础内容
    if isinstance(user_input, list):
        base = user_input
    else:
        base = build_messages(user_input, history)

    last_message = ""
    unknow = False
    #判断是否泄露
    leaked = False
    empty = False

    for attempt in range(max_retries):
        # 第 2 次起给用户那句话补个提示，绕开"空响应"的解析问题
        messages = base if attempt == 0 else _nudged(base)
        try:
            resp = ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=messages,
                tools=TOOLS_FOR_AI,
                options={"temperature": 0, "seed": 42 + attempt},
            )
            msg = resp["message"]
            tool_calls = msg.get("tool_calls") or []
            #防止幻觉
            if len(tool_calls) > 1:
                print(f"[recognize] 注意：AI 调了 {len(tool_calls)} 个工具，只用了第一个")
            #成功呼叫一个工具
            if tool_calls:
                call = tool_calls[0]
                tool_name = call["function"]["name"]
                tool_args = call["function"]["arguments"]
                print(f"[recognize 第 {attempt + 1} 次] ✅ tool={tool_name} args={tool_args}")
                return {"ok": True, "tool": tool_name, "args": tool_args}
            #记录大模型的内容
            content = msg.get("content") or ""
            print(f"[recognize 第 {attempt + 1} 次] ⚠️ 没调工具，content={content!r}")
            #初始化
            #记录内容
            last_message = content
            leaked = empty = False
            #没有回应
            if not content.strip():
                empty = True
                print(f"[recognize 第 {attempt + 1} 次] 🕳 空响应，下一轮补提示重试")
                continue
            #尝试捞出tool call
            recovered = _recover_tool_call(content)
            if recovered:
                print(f"[recognize] ♻️ 从泄漏文本中恢复 tool={recovered['name']} "
                      f"args={recovered['args']}")
                return {"ok": True, "tool": recovered["name"], "args": recovered["args"],
                        "recovered": True}
            #产生泄露
            if _is_tool_leak(content):
                leaked = True
                print(f"[recognize 第 {attempt + 1} 次] ⚠️ tool_call 泄漏但解析失败，重试")
                continue
            #允许循环
            if retry_text and attempt == 0:
                print(f"[recognize 第 {attempt + 1} 次] 💬 文字回复，循环模式下再试一次")
                continue
            return {"ok": True, "is_txt": True, "message": content}
        except Exception as e:
            print(f"[recognize 第 {attempt + 1} 次] ❌ 异常：{e}")
            last_message = str(e)
            unknow = True

    print(f"[recognize] ❌ {max_retries} 次都失败")

    # 失败统一给一句用户能看懂的话（异常堆栈只在日志里）
    if unknow:
        print(f"[recognize] 最后一次异常：{last_message}")
        return {"ok": False, "message": "AI 服务暂时不可用，请稍后重试。"}
    if empty:
        return {"ok": False, "message": "没能理解这个请求，请换个说法试试。"}
    if not last_message:
        return {"ok": False, "message": "AI 没有返回内容，请重试。"}
    if leaked:
        return {"ok": False, "message": "没能理解这个请求，请换个说法试试。"}

    return {"ok": True, "is_txt": True, "message": last_message}
