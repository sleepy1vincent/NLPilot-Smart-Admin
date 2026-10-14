import ollama

from config import Config
from prompts.system_prompt import SYSTEM_PROMPT
from services.tools import TOOLS_FOR_AI

def _is_tool_leak(content: str) -> bool:
    """检测 AI 输出是否泄漏了 tool_call 语法"""
    if not content:
        return False
    markers = ["<tool_call>", "</tool_call>", '{"name":', '"arguments"', "leton"]
    return any(m in content for m in markers)
def recognize(user_input:str,history:list=None,max_retries:int=3)->dict:
    messages=[{"role":"system","content":SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-4:])
    messages.append({"role":"user","content":user_input})
    last_message=""
    unknow=False
    for attempt in range(max_retries):
        try:
            resp= ollama.chat(
                model=Config.OLLAMA_MODEL,
                messages=messages,
                tools=TOOLS_FOR_AI,
                options={
                    "temperature":0,
                    "seed":42+attempt,
                },
            )
            msg=resp["message"]
            tool_calls=msg.get("tool_calls")or[]
            if len(tool_calls) > 1:
                print(f"[recognize] 注意：AI 调了 {len(tool_calls)} 个工具，只用了第一个")
            if tool_calls:
                call=tool_calls[0]
                tool_name=call["function"]["name"]
                tool_args=call["function"]["arguments"]
                print(f"[recognize 第 {attempt + 1} 次] ✅ tool={tool_name} args={tool_args}")
                return{
                    "ok":True,
                    "tool":tool_name,
                    "args":tool_args,
                }
            print(f"[recognize 第 {attempt + 1} 次] ⚠️ 没调工具，content={msg.get("content", "")}")
            last_message=msg.get("content")
            if _is_tool_leak(last_message):
                print(f"[recognize 第 {attempt + 1} 次] ⚠️ tool_call 泄漏，跳过")
                continue
            unknow=False
        except Exception as e:
            print(f"[recognize 第 {attempt + 1} 次] ❌ 异常：{e}")
            last_message=str(e)
            unknow =True
    print(f"[recognize] ❌ {max_retries} 次都失败，返回文字回复")
    if unknow:
        return{
            "ok":False,
            "message":last_message,
            "reply":"未知错误"
        }
    elif not last_message:
        return {
            "ok": False,
            "message": "AI返回为空",
            "reply": "AI未应答",
        }
    else:
        return{
            "ok":True,
            "is_txt":True,
            "message":last_message,
            "reply":last_message
        }