"""工具层：11 个可被模型调用的函数

返回协议（所有工具统一）
------------------------
查询类
    {"ok": True, "count": N, "data": [...], "is_rag": bool}
        is_rag=True 表示结果来自向量检索（不是 SQL）

推荐类
    {"ok": True, "count": N, "data": [{..., "reason": "推荐理由"}]}

变更类（真实写库）
    {"ok": True, "affected": N, "message": "..."}
    {"ok": True, "id": 12, ...}            新增
    {"ok": True, "sale_id": 33, "new_stock": 95}      销售
    {"ok": True, "purchase_id": 8, "new_stock": 60}   进货
    {"ok": True, "affected": 0, "message": "...没有变化"}   值相同（不算成功变更）

提案类（**不写库**，等前端二次确认）
    {"ok": True, "need_confirm": True, "action": "delete|discount",
     "target": "iPhone15", "message": "即将删除…确认吗？"}

失败
    {"ok": False, "message": "原因"}
    {"ok": False, "message": "...", "candidates": [...], "hint": "..."}   可自我纠正的错误

硬规则
------
  · 副作用只能在这里发生（agent 层不直接碰 DAO）
  · 写操作必须走事务；扣库存前先 SELECT ... FOR UPDATE 加行锁
  · `affected == 0` 一律不算成功（不能用"没变化"冒充"已修改"）
"""
import re

from db import Transaction
from dao import product_dao, purchases_dao, sales_dao
from services import rag_services, enrich_services

DISTANCE_THRESHOLD =0.53

# 并列问法的分隔符："A 和 B"、"A、B"、"A，B"、"A / B"
_NAME_SPLIT = re.compile(r"\s*(?:以及|和|与|、|，|,|；|;|/|\+)\s*")


def _to_float(v):
    """模型常把数字传成字符串（如 "500"、"¥500"、"500元"），这里统一转成 float。"""
    # 去掉货币符号、千分位、"元/块"等单位，只留数字和小数点
    s = re.sub(r"[^\d.\-]", "", str(v).replace(",", "").replace("，", ""))
    try:
        return float(s) if s else None
    except ValueError:
        return None
def _to_bool(v):
    """模型常把布尔传成字符串（如 "true"、"是"、"有"）。"""
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "y", "是", "有")
# ============ CRUD ============
def query_products(name: str | None = None, category: str | None = None,
                   max_price: float | None = None, min_price: float | None = None,
                   in_stock: bool | None = None, sort: str | None = None,
                   top_k: int | None = None, nth: int | None = None) -> dict:
    """查询商品。支持按名字、品类、价格区间、是否有货组合筛选，用户没给条件时返回全部。

    使用场景（重要）：
      "有哪些手机"          -> category="手机"
      "500 元以内有什么"    -> max_price=500
      "500 以内还有货的"    -> max_price=500, in_stock=true
      "最便宜的配件"        -> category="配件", sort="price_asc"
      "库存最多的"          -> sort="stock_desc"
      "查 iPhone15"         -> name="iPhone15"

    【排序 / 第 N 个】
      "最便宜的"        -> sort="price_asc", nth=1
      "第三便宜的"      -> sort="price_asc", nth=3
      "最贵的"          -> sort="price_desc", nth=1
      "第二贵的"        -> sort="price_desc", nth=2
      "库存最少的"      -> sort="stock_asc", nth=1
      传了 nth 时，工具只返回第 N 名那一条，不会返回整个列表——
      不需要你自己数，直接看返回的那条就是答案。
      传了 sort 但不传 nth 时，返回列表每条带 rank，message 里也写好了名次。

    【禁止】不要把价格、品类、库存等筛选条件写进 name 参数。
      name 只放商品名关键词；价格用 max_price/min_price，品类用 category。
      例：用户说"500 块以内送什么好"，应传 max_price=500，而不是 name="500块以内"。

    查不到时如实说明，不要编造商品。

    Args:
      name: 商品名关键词，模糊匹配。仅当用户明确提到商品名（如 iPhone15、AirPodsPro）时使用
      category: 品类，可选值：手机 / 耳机 / 电脑 / 平板 / 穿戴 / 显示器 / 配件
      max_price: 价格上限（元），用户说"500 以内""不超过 300"时使用
      min_price: 价格下限（元），用户说"至少 1000""1000 以上"时使用
      in_stock: 传 true 表示只返回还有库存的商品，用户说"有货的"时使用
      sort: 排序方式，可选：price_asc（便宜在前）/ price_desc（贵在前）/ stock_desc（库存多在前）
      top_k: 只取前几个，不传时最多返回 50 条
      nth: 只要第 N 名那一条（配合 sort 使用）。问"第二贵"就传 sort="price_desc", nth=2，
           工具只返回那一条，不用自己数列表。
    """
    name = (name or "").strip()
    category = (category or "").strip()
    max_price = _to_float(max_price)
    min_price = _to_float(min_price)
    want_stock = _to_bool(in_stock)
    sort = (sort or "").strip() or None
    if sort not in ("price_asc", "price_desc", "stock_asc", "stock_desc"):
        sort = None

    try:
        limit = int(top_k) if top_k else 50
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 50))

    # nth（第 N 名）：给了 nth 就必须有排序，否则"第几个"没有意义
    try:
        nth = int(nth) if nth else None
    except (TypeError, ValueError):
        nth = None
    if nth is not None:
        nth = max(1, nth)
        if sort is None:
            sort = "price_asc"      # 兜底：问"第 N"多半是问价格序
        limit = 50                  # 要能取到第 N 个，先把完整列表拿回来

    has_filter = bool(category or max_price is not None or min_price is not None
                      or want_stock or sort)

    # "A 和 B 的库存" 这类并列问法：模型会把整串当**一个**名字传进来
    # （实测传的是 "小米手环8,罗技鼠标M590" 且带 in_stock=True），
    # 单条 LIKE 必然 0 条。拆成多个名字、各带同样的筛选条件分别查，再合并。
    # 这件事必须由代码做——模型既不会拆，也不会分两次调用。
    parts = [p.strip() for p in _NAME_SPLIT.split(name) if p.strip()] if name else []
    if len(parts) > 1:
        merged, seen_ids = [], set()
        for p in parts:
            if has_filter:
                sub = product_dao.query_products_filtered(
                    name=p, category=category or None,
                    max_price=max_price, min_price=min_price,
                    in_stock=want_stock, sort=sort, limit=limit,
                )
            else:
                sub = product_dao.query_products(p)
            for r in sub:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged.append(r)
        if merged:
            if sort:
                for i, r in enumerate(merged, 1):
                    r["rank"] = i
            return {"ok": True, "count": len(merged), "data": merged[:limit],
                    "is_rag": False,
                    "message": f"分别按 {len(parts)} 个商品名查询，共 {len(merged)} 条"}
        return {"ok": True, "count": 0, "data": [], "is_rag": False,
                "message": f"分别查了 {len(parts)} 个商品名，都没有找到"}

    if has_filter:
        rows = product_dao.query_products_filtered(
            name=name or None,
            category=category or None,
            max_price=max_price,
            min_price=min_price,
            in_stock=want_stock,
            sort=sort,
            limit=limit,
        )
        if not rows:
            return {"ok": True, "count": 0, "data": [], "is_rag": False,
                    "message": "没有找到符合条件的商品"}

        # nth：直接由代码取第 N 名，只返回那一条 —— 不让模型数列表
        if nth is not None:
            if nth > len(rows):
                return {"ok": True, "count": 0, "data": [], "is_rag": False,
                        "message": f"符合条件的只有 {len(rows)} 个，没有第 {nth} 个"}
            one = rows[nth - 1]
            one["rank"] = nth
            label = {"price_asc": "价格从低到高", "price_desc": "价格从高到低",
                     "stock_asc": "库存从少到多", "stock_desc": "库存从多到少"}.get(sort, sort)
            return {"ok": True, "count": 1, "data": [one], "is_rag": False,
                    "sorted_by": sort,
                    "message": f"按{label}排序，第{nth}名是 {one['name']}，¥{one['price']}"}

        # 排序时给每条打上名次：模型数不清"第几个"，直接把 rank 交给它
        if sort:
            for i, r in enumerate(rows, 1):
                r["rank"] = i
            # 再把名次写成一句话——7B 对"从列表里数第 N 条"不可靠，
            # 但"照抄一句话"很可靠。两种形式都给，总有一个能用上。
            label = {"price_asc": "价格从低到高", "price_desc": "价格从高到低",
                     "stock_asc": "库存从少到多", "stock_desc": "库存从多到少"}.get(sort, sort)
            head = "；".join(
                f"第{r['rank']}名 {r['name']} ¥{r['price']}" for r in rows[:5]
            )
            more = f"…（共 {len(rows)} 条）" if len(rows) > 5 else ""
            return {"ok": True, "count": len(rows), "data": rows, "is_rag": False,
                    "sorted_by": sort,
                    "message": f"按{label}排序：{head}{more}"}
        return {"ok": True, "count": len(rows), "data": rows, "is_rag": False}

    rows = product_dao.query_products(name or None)
    if rows:
        return {"ok": True, "count": len(rows), "data": rows[:limit], "is_rag": False}
    # 如果数据库查询不到，则尝试rag查询
    if name:
        hits = rag_services.search_products(name, top_k=3)
        hits = [(int(i), d) for i, d in hits if d <= DISTANCE_THRESHOLD]
        if hits:
            rows = product_dao.get_by_ids([i for i, _ in hits])
            if rows:
                return {"ok": True, "count": len(rows), "data": rows, "is_rag": True}

    return {"ok": True, "count": len(rows), "data": rows, "is_rag": False}

# 只保留"离最优不远"的候选（相对阈值）。比绝对阈值可靠：距离分布随语料变化，
# 但"和第一名差多少"是稳定的尺度。
RECOMMEND_MARGIN = 0.08
# 连最优候选都太远 → 说明库里没有贴合的，如实说没有，不硬推。
# 实测标定：库里"有对应商品"的最优距离 0.310~0.518，"没有"的是 0.580~0.623，
# 间隙在 0.518~0.580，取中间值 0.55（两侧都留余量）。
RECOMMEND_MAX_DISTANCE = 0.55


def recommend_products(occasion: str | None = None, budget: float | None = None,
                       top_k: int | None = None) -> dict:
    """根据用途 / 受众 / 预算推荐几个商品。用户说"推荐""送人""适合什么""有什么好""帮我挑"时用它。

    内部流程：语义宽召回候选 → 按预算和库存硬过滤 → 按贴合度排序 → 取前 N 个并附推荐理由。
    每个结果带 reason 字段。

    使用场景：
      "推荐个送女朋友的礼物"   -> occasion="送女朋友"
      "有什么适合学生党的"     -> occasion="学生党"
      "500 以内送什么好"      -> occasion="送礼", budget=500
      "推荐个降噪耳机"         -> occasion="降噪耳机"

    【禁止】不要用 query_products 代替本工具；不要把用途写进 budget，也不要把预算写进 occasion。

    Args:
      occasion: 用途、受众或需求，直接用用户原话里的关键词，如"送女朋友""学生党""办公""降噪""旅行"
      budget: 预算上限（元），用户说"500 以内""不超过 300"时使用
      top_k: 推荐几个，默认 3，取值 1-5
    """
    occasion = (occasion or "").strip()
    budget = _to_float(budget)
    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        top_k = 3
    top_k = max(1, min(top_k, 5))

    # 商品（按语义召回的 id 回查）
    rows = []
    # 向量距离：id -> distance
    dist = {}
    if occasion:
        try:
            hits = rag_services.search_products(occasion, top_k=10)
            dist = {int(i): float(d) for i, d in hits}
            if dist:
                rows = product_dao.get_by_ids(list(dist.keys()))
        except Exception as ex:
            print(f"[推荐] 语义召回失败: {ex}")
            dist, rows = {}, []

        # 给了用途却拿不到任何语义候选 → 如实报错，绝不退回全量凑数
        if not dist:
            return {"ok": False, "count": 0, "data": [], "is_rag": False,
                    "message": "语义检索暂时不可用，没法按用途推荐。"
                               "可以先用「有哪些商品」看看库存。"}
    else:
        # 没给用途（例如只说"500 以内有什么"）→ 才允许在全部商品里按预算挑
        rows = product_dao.query_products()

    if occasion and dist:
        # 只保留"库里真实存在"的召回结果。索引可能残留已删除商品的向量（幽灵），
        # 若让幽灵参与，它会以极小的距离主导阈值，真实商品全被判"太远"。
        real = {r["id"]: dist[r["id"]] for r in rows if r.get("id") in dist}
        if not real:
            return {"ok": False, "count": 0, "data": [], "is_rag": True,
                    "message": f"库里的商品和「{occasion}」都对不上"}

        # 锚点 = 最接近的真实商品（**不看预算**）。
        # 若用"买得起的里面最好的"当锚，标准会被悄悄放松，
        # 把明显更不相关的商品也当成"符合"。
        anchor = min(real.values())
        if anchor > RECOMMEND_MAX_DISTANCE:
            return {"ok": False, "count": 0, "data": [], "is_rag": True,
                    "message": f"库里没有适合「{occasion}」的商品（最接近的也差得远）"}

        # 第一遍：相关性——只留和最优差不多近的
        cutoff = anchor + RECOMMEND_MARGIN
        rows = [r for r in rows if real.get(r["id"], float("inf")) <= cutoff]

    # 第二遍：硬约束——买得起吗、有货吗
    if budget is not None:
        rows = [r for r in rows
                if _to_float(r.get("price")) is not None
                and _to_float(r.get("price")) <= budget]
    rows = [r for r in rows if (r.get("stock") or 0) > 0]

    if not rows:
        if occasion and dist:
            return {"ok": False, "count": 0, "data": [], "is_rag": True,
                    "message": f"有和「{occasion}」很接近的商品，但都不符合当前的预算或库存条件"}
        cond = []
        if occasion:
            cond.append(f"用途「{occasion}」")
        if budget is not None:
            cond.append(f"预算 {budget:g} 元")
        return {"ok": False, "count": 0, "data": [], "is_rag": bool(dist),
                "message": "没有找到符合条件的商品（" + "、".join(cond or ["当前条件"]) + "）"}

    shown = occasion if len(occasion) <= 12 else occasion[:12] + "…"
    if occasion and dist:
        rows.sort(key=lambda r: dist.get(r["id"], float("inf")))

    picked = rows[:top_k]

    # 附推荐理由（取自描述，不额外调模型）
    for r in picked:
        desc = (r.get("description") or "").strip()
        r["reason"] = desc[:40] if desc else (r.get("tags") or "")

    if occasion and len(picked) < top_k:
        message = f"库里符合「{shown}」的只有 {len(picked)} 个，都已列出"
    else:
        message = f"为你挑了 {len(picked)} 个" + (f"（{shown}）" if occasion else "")

    return {"ok": True, "count": len(picked), "data": picked, "is_rag": bool(dist),
            "message": message}
def create_product(name: str, price: float = 0, stock: int = 0) -> dict:
    """新增商品。如果用户没给价格或库存，你要自己生成合理值。"""
    name = (name or "").replace(" ", "").strip()
    if not name:
        return {"ok": False, "message": "缺少商品名"}
    if product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 已存在"}
    new_id = product_dao.insert_product(name, price, stock)
    try:
        e = enrich_services.tag(name)
        if e:
            product_dao.save_enrichment(
                new_id,
                e.get("category") or "",
                ",".join(e.get("tags") or []),
                e.get("description") or "",
            )
    except Exception as ex:
        print(f"[打标] 失败 id={new_id}: {ex}")

    try:
        row = product_dao.get_by_ids([new_id])
        if row:
            rag_services.upsert_product(row[0])
    except Exception as ex:
        print(f"[RAG] 同步失败 id={new_id}: {ex}")
    return {"ok": True, "id": new_id, "message": f"新增成功：{name}"}
def update_product(name: str, price: float = None, stock: int = None) -> dict:
    """修改商品的价格或库存。"""
    name = (name or "").replace(" ", "").strip()
    if not product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 不存在"}
    fields = {}
    if price is not None:
        fields["price"] = price
    if stock is not None:
        fields["stock"] = stock
    if not fields:
        return {"ok": False, "message": "没有可修改的字段"}
    rows = product_dao.update_product(name, fields)
    if rows == 0:
        return {"ok": True, "affected": 0, "message": f"{name} 的值没有变化"}
    return {"ok": True, "affected": rows, "message": f"修改成功：{name}"}
def delete_product(name: str) -> dict:
    """删除商品（需要用户确认）。"""
    name = (name or "").replace(" ", "").strip()
    if not product_dao.get_by_name(name):
        return {"ok": False, "message": f"商品 {name} 不存在"}
    return {
        "ok": True,
        "need_confirm": True,
        "action": "delete",
        "target": name,
        "message": f"即将删除商品「{name}」，确认吗？",
    }
def apply_discount(name:str,rate:float)->dict:
    """给指定的商品打折
        使用场景：用户输入为打折的时候使用，有具体减少数值请使用update_product
        参数：
        name:商品名
        rate：打折比例，0~1 之间。0.8 表示八折（即原价 × 0.8），
              0.5 表示半价，0.9 表示九折。
              如果用户输入的打折倍数不清楚、有误要提示并且再次询问
        返回：打折后的新价格
    """
    name = (name or "").replace(" ", "").strip()
    if rate<=0 or rate>=1:
        return {"ok":False,"message":"打折倍数不正确"}
    product = product_dao.get_by_name(name)
    if not product:
        return {"ok":False,"message":"打折的商品不存在"}
    return {"ok":True,"need_confirm":True,"action":"discount","target":name,
            "message":f"将要进行打折的商品：{name},价格将变成{float(product['price'])*rate}确定吗?",
            "data":float(product['price'])*rate}
# =========== sale ===============
def record_sale(product_name: str, quantity: int, unit_price: float = None) -> dict:
    """
    记录一笔销售，并减少库存。

    【原子性】"写销售记录"和"扣库存"在同一个事务里完成：
    任一步失败，两步都会被回滚，不会出现"库存扣了但记录没写"。

    【并发】读取库存时加行锁（SELECT ... FOR UPDATE），
    防止两个请求同时读到同一个库存值而超卖。

    使用场景：
        用户说"卖了"、"出售"、"卖出"、"卖掉了 X 个 Y" 时使用。
    参数：
        product_name: 商品名。
        quantity: 销售数量（正整数）。
        unit_price: 单价（可选，不传用商品当前价）。
    返回：
        销售记录 ID + 剩余库存。
    """
    product_name = (product_name or "").replace(" ", "").strip()
    if not product_name:
        return {"ok": False, "message": "缺少商品名"}
    if not isinstance(quantity, int) or isinstance(quantity,bool) or quantity <= 0:
        return {"ok": False, "message": "售出数量必须是正整数"}
    if unit_price is not None and (
        not isinstance(unit_price, (int, float))
        or isinstance(unit_price, bool)
        or unit_price < 0
    ):
        return {"ok": False, "message": "售出单价不合法"}

    try:
        with Transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, price, stock FROM product_lists "
                    "WHERE name=%s FOR UPDATE",
                    (product_name,),
                )
                product = cur.fetchone()
                if not product:
                    return {"ok": False, "message": f"商品 {product_name} 不存在"}

                if quantity > product["stock"]:
                    return {"ok": False,
                            "message": f"库存不足：当前 {product['stock']}，请求 {quantity}"}

                price = float(product["price"]) if unit_price is None else unit_price
                sale_id = sales_dao.record_sale(
                    product_name, quantity, price, cursor=cur,
                    total=round(quantity * price, 2),
                )

                # 4) 扣库存（同一个游标 = 同一个事务）
                new_stock = product["stock"] - quantity
                cur.execute(
                    "UPDATE product_lists SET stock=%s WHERE name=%s",
                    (new_stock, product_name),
                )
        # with 正常退出 -> 一次性 commit
        return {
            "ok": True,
            "sale_id": sale_id,
            "new_stock": new_stock,
            "message": f"已记录销售：{product_name} × {quantity}，剩余库存 {new_stock}",
        }
    except Exception as e:
        # with 已在退出时 rollback
        return {"ok": False, "message": f"记录失败：{e}"}
def query_sales(name: str = None, days: int = None) -> dict:
    """
    查询销售记录。

    使用场景：用户说"卖了什么"、"销售记录"、"昨天卖了啥"时使用。

    参数：
        name: 商品名（可选，不传查全部）。
        days: 最近多少天（可选，不传查全部时间）。

    返回：销售记录列表。
    """
    name = (name or "").replace(" ", "").strip()
    rows = sales_dao.get_sales(product_name=name, days=days)
    return {
        "ok": True,
        "count": len(rows),
        "data": rows,
        "message": f"共 {len(rows)} 条销售记录",
    }
def sales_report(name: str = None, days: int = 7) -> dict:
    """
    销售报告 / 销售统计。**注意：这里只有"卖了多少"，没有"还剩多少"。**

    使用场景：用户说"销售情况"、"卖了多少钱"、"这周业绩"、"卖得最好的是什么"时使用。

    【重要】返回值里的 sold_quantity 是**销量**，不是库存。
    用户若问"还剩多少 / 库存多少"，必须另外用 query_products 查。
    只用本工具的销量去回答库存问题 = 答错。

    参数：
        name: 商品名（可选，不传查全部）。
        days: 最近多少天（默认 7）。
    返回：sold_quantity / total_amount / 订单数。
    """
    name = (name or "").replace(" ", "").strip()
    rows = sales_dao.get_sales(product_name=name, days=days)
    total_qty = sales_dao.total_sold(product_name=name, days=days)
    total_amount = sum(float(r["total"]) for r in rows)
    return {
        "ok": True,
        "count": len(rows),
        # 字段名直接写明是"卖出的"，避免模型把它当库存
        "sold_quantity": total_qty,
        "total_amount": round(total_amount, 2),
        "data": rows[:20],       # 最多 20 条明细
        "message": (
            f"最近 {days} 天卖出 {total_qty} 件、{len(rows)} 笔订单，"
            f"共 ¥{round(total_amount, 2)}。"
            f"（这是销量，不含库存；查库存请用 query_products）"
        ),
    }
# =========== purchases ===========
def record_purchase(product_name: str, quantity: int, unit_price: float = None) -> dict:
    """
    记录一笔进货，并增加库存。

    【原子性】"写进货记录"和"加库存"在同一个事务里完成：
    任一步失败，两步都会被回滚。

    【并发】读取库存时加行锁（SELECT ... FOR UPDATE）。

    使用场景：用户说"进了"、"进货"、"补货 X 个 Y"时使用。

    参数：
        product_name: 商品名。
        quantity: 数量（正整数）。
        unit_price: 进货单价（可选）。
    """
    product_name = (product_name or "").replace(" ", "").strip()
    if not product_name:
        return {"ok": False, "message": "缺少商品名"}
    if not isinstance(quantity, int) or isinstance(quantity,bool) or quantity <= 0:
        return {"ok": False, "message": "数量必须是正整数"}
    if unit_price is not None and (
        not isinstance(unit_price, (int, float))
        or isinstance(unit_price, bool)
        or unit_price < 0
    ):
        return {"ok": False, "message": "进货单价不合法"}

    try:
        with Transaction() as conn:
            with conn.cursor() as cur:
                # 读库存并加行锁
                cur.execute(
                    "SELECT id, name, price, stock FROM product_lists "
                    "WHERE name=%s FOR UPDATE",
                    (product_name,),
                )
                product = cur.fetchone()
                if not product:
                    return {"ok": False, "message": f"商品 {product_name} 不存在"}

                price = float(product["price"]) if unit_price is None else unit_price

                # 2) 写进货记录（同一个事务）
                purchase_id = purchases_dao.record_purchase(
                    product_name, quantity, price, cursor=cur,
                    total=round(quantity * price, 2),
                )

                # 3) 加库存（同一个事务）
                new_stock = product["stock"] + quantity
                cur.execute(
                    "UPDATE product_lists SET stock=%s WHERE name=%s",
                    (new_stock, product_name),
                )
        # with 正常退出 -> 一次性 commit
        return {
            "ok": True,
            "purchase_id": purchase_id,
            "new_stock": new_stock,
            "message": f"已记录进货：{product_name} × {quantity}，剩余库存 {new_stock}",
        }
    except Exception as e:
        # with 已在退出时 rollback
        return {"ok": False, "message": f"记录失败：{e}"}
def query_purchases(name: str = None, days: int = None) -> dict:
    """
    查询进货记录。

    使用场景：用户说"进了什么"、"进货记录"、"最近补货"时使用。

    参数：
        name: 商品名（可选）。
        days: 最近多少天（可选）。

    返回：进货记录列表。
    """
    rows = purchases_dao.get_purchase(product_name=name, days=days)
    return {
        "ok": True,
        "count": len(rows),
        "data": rows,
        "message": f"共 {len(rows)} 条进货记录",
    }
# ========== 对话型工具（不碰数据库，只表达"我需要什么"）=========
# 这两个工具的存在意义：让模型**用结构化参数**表达反问/拒绝，
# 而不是自由生成一句话。文本由 services/reply_templates.py 渲染。
def clarify(field: str, candidates: str = "") -> dict:
    """信息不足，需要向用户追问。

    Args:
      field: 缺少什么，只能取以下之一：
             name（商品名）/ quantity（数量）/ price（价格）/ stock（库存）
             / target（要操作哪个）/ which_one（有多个候选，请用户挑一个）
      candidates: 仅 which_one 时使用，逗号分隔的候选商品名
    """
    return {"ok": False, "kind": "clarify", "field": field, "candidates": candidates}
def refuse(reason: str) -> dict:
    """无法处理这个请求，需要拒绝。

    Args:
      reason: 只能取以下之一：
              chat（闲聊，与商品无关）/ policy（退换货、发票等政策问题）
              / unknown_goods（库里没有该商品）/ out_of_scope（超出能力范围）
    """
    return {"ok": False, "kind": "refuse", "reason": reason}
# ============ 工具注册表 ============
TOOL_FUNCTIONS = {
    # 商品
    "query_products": query_products,
    "recommend_products": recommend_products,
    "create_product": create_product,
    "update_product": update_product,
    "delete_product": delete_product,
    "apply_discount": apply_discount,
    # 销售
    "record_sale": record_sale,
    "query_sales": query_sales,
    "sales_report": sales_report,
    # 进货
    "record_purchase": record_purchase,
    "query_purchases": query_purchases,
    # 对话（不写库）
    "clarify": clarify,
    "refuse": refuse,
}
# 传给 Ollama 的工具列表
TOOLS_FOR_AI = list(TOOL_FUNCTIONS.values())