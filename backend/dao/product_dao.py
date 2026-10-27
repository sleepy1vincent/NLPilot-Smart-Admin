from db import get_conn

# 排序白名单：只允许这些固定值，绝不把用户输入拼进 SQL
_SORT_MAP = {
    "price_asc": "price ASC",
    "price_desc": "price DESC",
    "stock_asc": "stock ASC",
    "stock_desc": "stock DESC",
}
def query_products_filtered(name=None, category=None, max_price=None,
                            min_price=None, in_stock=False, sort=None, limit=50):
    """
    带结构化条件的查询（品类 / 价格区间 / 是否有货 / 排序）。
    与 query_products 的区别：
      - query_products 只按名字模糊查
      - 本函数支持组合条件，用于"有哪些耳机""500 以内""有货的"这类需求、
    category 用 LIKE 而不是 =：
      因为库里的 category 是 LLM 打的自由值，存在 "手机/手表" 这种复合值，
      用 = 会漏掉它。等 category 归一化后可以改成精确匹配。
    """
    sql = ("SELECT id, name, price, stock, category, tags, description, last_update "
           "FROM product_lists WHERE 1=1")
    args = []
    #名字有限制
    if name:
        sql += " AND name LIKE %s"
        args.append(f"%{name}%")
    if category:
        sql += " AND category LIKE %s"
        args.append(f"%{category}%")
    if max_price is not None:
        sql += " AND price <= %s"
        args.append(max_price)
    if min_price is not None:
        sql += " AND price >= %s"
        args.append(min_price)
    if in_stock:
        sql += " AND stock > 0"

    sql += " ORDER BY " + _SORT_MAP.get(sort or "", "id ASC") + " LIMIT %s"
    args.append(int(limit))

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        conn.close()
def query_products(name=None):
    """模糊查询"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if name:
                cur.execute(
                    "SELECT id, name, price, stock, category, tags, description, last_update "
                    "FROM product_lists WHERE name LIKE %s ORDER BY id",
                    (f"%{name}%",),
                )
            else:
                cur.execute(
                    "SELECT id, name, price, stock, category, tags, description, last_update "
                    "FROM product_lists ORDER BY id"
                )
            return cur.fetchall()
    finally:
        conn.close()
def get_by_name(name):
    """精确查询"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, price, stock FROM product_lists WHERE name=%s",
                (name,),
            )
            return cur.fetchone()
    finally:
        conn.close()
def insert_product(name, price, stock):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO product_lists (name, price, stock) VALUES (%s,%s,%s)",
                        (name, price, stock))
            new_id = cur.lastrowid
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return new_id
def update_product(name, fields, conn=None):
    """
    更新商品的价格/库存，返回受影响行数。
    事务边界由调用方决定：
      - 不传 conn：自己开连接、自己 commit
      - 传了 conn：在调用方的连接上执行，【不 commit、不 close】
    """
    if not fields:
        return 0

    def _run(c):
        with c.cursor() as cur:
            set_clause = ", ".join(f"{k}=%s" for k in fields)
            sql = f"UPDATE product_lists SET {set_clause} WHERE name=%s"
            cur.execute(sql, (*fields.values(), name))
            return cur.rowcount

    if conn is not None:
        return _run(conn)

    own = get_conn()
    try:
        rows = _run(own)
        own.commit()
        return rows
    except Exception:
        own.rollback()
        raise
    finally:
        own.close()
def delete_product(name):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_lists WHERE name=%s", (name,))
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
def get_by_ids(ids):
    """按 id 批量查询（一次 SQL 拿回所有命中的商品）"""
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, name, price, stock, category, tags, description, last_update "
                f"FROM product_lists WHERE id IN ({placeholders})",
                tuple(ids),
            )
            return cur.fetchall()
    finally:
        conn.close()
def save_enrichment(product_id: int, category: str, tags: str, description: str):
    """只写字段，不做任何 LLM 调用（打标在上层完成）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE product_lists SET category=%s, tags=%s, description=%s WHERE id=%s",
                (category, tags, description, product_id))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
