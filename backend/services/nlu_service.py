import json
import re

import ollama

from config import Config
from prompts.system_prompt import SYSTEM_PROMPT
from services.tools import TOOLS_FOR_AI, TOOL_FUNCTIONS


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


def recognize(user_input: str, history: list = None, max_retries: int = 3) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_input})

    last_message = ""
    unknow = False
    leaked = False

    for attempt in range(max_retries):
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
            print(f"[recognize 第 {attempt + 1} 次] ⚠️ 没调工具，content={content}")
            last_message = content
            leaked = False

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

            # 正常的文字回复：再给一次机会让它改调工具；第二次仍是文字就接受，
            # 不为了"可能调工具"把每次闲聊都拖成 3 次调用。
            if attempt == 0:
                print(f"[recognize 第 {attempt + 1} 次] 💬 文字回复，再试一次")
                continue
            return {"ok": True, "is_txt": True, "message": content, "reply": content}
        except Exception as e:
            print(f"[recognize 第 {attempt + 1} 次] ❌ 异常：{e}")
            last_message = str(e)
            unknow = True

    print(f"[recognize] ❌ {max_retries} 次都失败")

    if unknow:
        return {"ok": False, "message": last_message, "reply": "未知错误"}
    if not last_message:
        return {"ok": False, "message": "AI返回为空", "reply": "AI未应答"}
    if leaked:
        # 全是泄漏且解析不了：不要把那段乱码给用户看
        return {"ok": False,
                "message": "没能理解这个请求，请换个说法试试。",
                "reply": "没能理解这个请求，请换个说法试试。"}

    return {"ok": True, "is_txt": True, "message": last_message, "reply": last_message}
