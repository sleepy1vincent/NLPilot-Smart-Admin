
import json
import re
import ollama
from config import Config

ALIAS = {
    "平板电脑": "平板", "笔记本电脑": "电脑", "笔记本": "电脑",
    "手环/手表": "穿戴", "手环": "穿戴", "手表": "穿戴",
    "鼠标": "配件", "键盘": "配件", "充电宝": "配件",
    "移动电源": "配件", "数据线": "配件", "充电器": "配件",
}

def normalize_category(raw: str) -> str:
    c = (raw or "").strip()
    return ALIAS.get(c, c) if c else ""

PROMPT = """你是电商商品运营。根据商品名，生成便于搜索的信息。
要求：
1. category 只能是其一：手机、耳机、电脑、平板、穿戴、显示器、配件、其他
2. tags 给 3-5 个用户可能搜索的场景词（办公、听歌、追剧、运动、送礼、防水、降噪、便携…）
3. description 40 字以内，写清使用场景
4. 不要用"随时随地""畅享""美好瞬间"这类空泛词
5. 商品名不像真实商品时（纯数字、乱码），category 填"其他"
只输出 JSON：{"category":"...","tags":["..."],"description":"..."}"""

def tag(name: str) -> dict:
    """调 LLM 生成 category / tags / description。失败返回 {}，不抛异常。"""
    try:
        r = ollama.chat(
            model=Config.OLLAMA_MODEL,
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": f"商品名：{name}"}],
            format="json",
            options={"temperature": 0},
        )
        txt = r["message"]["content"]
        try:
            e = json.loads(txt)
        except Exception:
            m = re.search(r"\{.*\}", txt, re.S)
            e = json.loads(m.group(0)) if m else {}
        e["category"] = normalize_category(e.get("category"))
        return e
    except Exception as ex:
        print(f"[打标] 失败 {name}: {ex}")
        return {}