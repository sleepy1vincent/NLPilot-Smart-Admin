"""意图识别层：只负责「和模型说一次话」。

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

# 重试时追加的提示。必须**中性**：既要能救回"该调工具却回了文字"的情况，
# 又不能把闲聊硬掰成"去查商品"。
# （早期版本写的是"（请用工具查询，不要直接回答）"——它把闲聊逼成了查全部商品）
_NUDGE = "（如果用户是在闲聊，直接回答即可；如果要查数据或改数据，请调用工具）"


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


def _is_tool_leak(content: str) -> bool:
    """检测 AI 输出是否泄漏了 tool_call 语法"""
    if not content:
        return False
    markers = ["<tool_call>", "</tool_call>", '{"name":', '"arguments"', "leton"]
    return any(m in content for m in markers)


# 泄漏的 tool_call 形如：
#   leton\n{"name": "query_products", "arguments": {"category": "穿戴"}}</tool_call>
_LEAK_CALL = re.compile(
    r'\{\s*"name"\s*:\s*"([A-Za-z_]\w*)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
    re.S,
)


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
        return None
    name, raw_args = m.group(1), m.group(2)
    if name not in TOOL_FUNCTIONS:
        return None
    try:
        args = json.loads(raw_args)
    except Exception:
        return None
    return {"name": name, "args": args if isinstance(args, dict) else {}}


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
    if isinstance(user_input, list):
        base = user_input
    else:
        base = build_messages(user_input, history)

    last_message = ""
    unknow = False
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
            if len(tool_calls) > 1:
                print(f"[recognize] 注意：AI 调了 {len(tool_calls)} 个工具，只用了第一个")
            if tool_calls:
                call = tool_calls[0]
                tool_name = call["function"]["name"]
                tool_args = call["function"]["arguments"]
                print(f"[recognize 第 {attempt + 1} 次] ✅ tool={tool_name} args={tool_args}")
                return {"ok": True, "tool": tool_name, "args": tool_args}

            content = msg.get("content") or ""
            print(f"[recognize 第 {attempt + 1} 次] ⚠️ 没调工具，content={content!r}")
            last_message = content
            leaked = empty = False

            # ① 空响应：既没工具也没文字 → 算失败，下一轮补提示重试
            if not content.strip():
                empty = True
                print(f"[recognize 第 {attempt + 1} 次] 🕳 空响应，下一轮补提示重试")
                continue

            # ② tool_call 泄漏成文本：能解析就解析，不能就重试
            if _is_tool_leak(content):
                leaked = True
                recovered = _recover_tool_call(content)
                if recovered:
                    print(f"[recognize] ♻️ 从泄漏文本中恢复 tool={recovered['name']} "
                          f"args={recovered['args']}")
                    return {"ok": True, "tool": recovered["name"], "args": recovered["args"],
                            "recovered": True}
                print(f"[recognize 第 {attempt + 1} 次] ⚠️ tool_call 泄漏且无法解析，重试")
                continue

            # ③ 正常文字回复。
            #    单步模式（retry_text=False）：直接接受。
            #    实测"在吗"第 1 次答得很好，第 2 次却被 nudge 逼成 query_products()，
            #    拉出 27 条商品 —— 那条重试在**制造**问题。
            #    多步模式（retry_text=True）：再试一次，因为"查完再打八折"这种，
            #    第 1 步如果回了文字，第 2 步的动作就丢了。
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
