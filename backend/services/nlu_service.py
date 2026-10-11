import json
import re
import ollama
from config import Config
from prompts.system_prompt import SYSTEM_PROMPT
from services.tools import TOOLS_FOR_AI


def _extract_json(text: str) -> dict:
    """从模型输出里稳健地提取 JSON（回退方案用）"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    # 找第一个 { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"未找到 JSON：{text}")
    return json.loads(m.group(0))


def recognize(user_input: str, history: list = None, max_retries: int = 3) -> dict:
    """
    调 Ollama，让 AI 决定调哪个工具。

    如果 AI 没调工具（tool_calls 为空），重试最多 max_retries 次。
    每次用不同的 seed，避免"同样失败"。

    参数：
        user_input: 用户自然语言输入。
        history: 对话历史（最近 N 条），格式 [{"role": "user"/"assistant", "content": "..."}]
        max_retries: 最大重试次数（默认 3）。

    返回：
        成功：{"tool": "工具名", "args": {...}}
        失败：{"reply": "AI 的文字回复"}
        异常：{"error": "错误信息"}
    """
    # 1. 组装 messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if history:
        messages.extend(history[-4:])       # 最近 2 轮（4 条）
    messages.append({"role": "user", "content": user_input})

    # 2. 重试循环
    last_content = ""
    for attempt in range(max_retries):
        try:
            resp = ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=messages,
                tools=TOOLS_FOR_AI,
                options={
                    "temperature": 0,
                    "seed": 42 + attempt,   # ⚠️ 每次不同 seed
                },
            )

            msg = resp["message"]
            tool_calls = msg.get("tool_calls") or []

            if tool_calls:
                call = tool_calls[0]        # ⚠️ 只取第一个
                tool_name = call["function"]["name"]
                tool_args = call["function"]["arguments"]

                print(f"[recognize 第 {attempt + 1} 次] ✅ tool={tool_name} args={tool_args}")

                return {
                    "tool": tool_name,
                    "args": tool_args,
                }

            # ⚠️ 没调工具
            last_content = msg.get("content", "") or ""
            print(f"[recognize 第 {attempt + 1} 次] ⚠️ 没调工具，content={last_content[:100]}")

            # 多个 tool_calls 的情况（我们只取第一个，但记一下）
            if len(tool_calls) > 1:
                print(f"[recognize] 注意：AI 调了 {len(tool_calls)} 个工具，只用了第一个")

        except Exception as e:
            print(f"[recognize 第 {attempt + 1} 次] ❌ 异常：{e}")
            last_content = str(e)

    # 3. 所有重试失败
    print(f"[recognize] ❌ {max_retries} 次都失败，返回文字回复")
    return {
        "reply": last_content or "抱歉，我没理解你的意思，请换种说法或重试",
    }