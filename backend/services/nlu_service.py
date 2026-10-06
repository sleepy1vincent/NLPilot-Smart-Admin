import json
import re
import ollama
from config import Config
from prompts.system_prompt import SYSTEM_PROMPT


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"模型未输出合法 JSON：{text}")
    return json.loads(match.group(0))


def recognize(user_input: str) -> dict:
    try:
        resp = ollama.chat(
            model=Config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            options={"temperature": 0},
        )
        content = resp["message"]["content"]
        return _extract_json(content)
    except Exception as e:
        return {"intent": "unknown", "error": str(e)}