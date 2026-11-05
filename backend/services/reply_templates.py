"""对话文本模板：给用户看的话都由这里渲染，模型只出结构化参数。"""

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
def render_clarify(slots: str, candidates: str = "") -> str:
    parts = [p.strip() for p in str(slots or "").split(",") if p.strip()]
    if not parts:
        return FALLBACK
    text = "请补充：" + " / ".join(parts)
    if candidates:
        text += "\n可选：" + candidates
    return text
def render_refuse(reason: str) -> str:
    return REFUSE.get(reason, FALLBACK)
