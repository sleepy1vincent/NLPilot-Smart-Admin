"""对话文本模板

------------------
模型自由生成文字带来过三类事故（都是实测）：
  1. 「在吗」被重试掰成 query_products() → 拉出 27 条商品
  2. 伪造了"共 3 条：· 华为MateBook D15 ¥4299 库存67"——库里没有这个商品
  3. 「卖得最好的还剩多少库存」把销量 5 说成库存 5（实际 138）

结论：**模型可以决定"做什么"，但不能决定"怎么说"。**

现在的分工：
    模型 → 只输出结构化意图（tool + 受限参数）
    代码 → 从这里选一句话渲染给用户

模型能说的只有：
    clarify(field=...)   → 六个预设字段之一
    refuse(reason=...)   → 四个预设原因之一
    什么都没调           → FALLBACK（固定话术）
"""

#追问
CLARIFY = {
    "name":       "请告诉我要操作的商品名。",
    "quantity":   "请告诉我要操作的数量（正整数）。",
    "price":      "请告诉我价格。",
    "stock":      "请告诉我库存数量。",
    "target":     "请告诉我具体是哪个商品。",
    "which_one":  "有多个匹配的商品，请指定一个：{candidates}",
}
#拒绝
REFUSE = {
    "chat":          "我只负责商品管理，闲聊帮不上忙。\n"
                     "你可以试试：查一下 iPhone15 的库存 / 推荐个 500 以内的礼物 / 卖了 2 个 AirPodsPro",
    "policy":        "退换货、发票这类政策问题我回答不了，请联系客服处理。",
    "unknown_goods": "库里没有这个商品。可以让我列出全部商品看看。",
    "out_of_scope":  "这个我做不到。我能做的是：查商品、推荐、改价格库存、记录销售与进货。",
}

# 模型违反约定（直接吐文字）时使用
FALLBACK = (
    "我没能理解这个请求。\n"
    "你可以这样说：\n"
    "· 查一下 iPhone15 的库存\n"
    "· 500 以内送女朋友什么好\n"
    "· 卖了 2 个 AirPodsPro"
)
#把上文的东西正确渲染
def render_clarify(field: str, candidates: str = "") -> str:
    text = CLARIFY.get(field)
    if not text:
        return FALLBACK
    if "{candidates}" in text:
        return text.format(candidates=candidates or "（没给出候选）")
    return text
def render_refuse(reason: str) -> str:
    return REFUSE.get(reason, FALLBACK)
