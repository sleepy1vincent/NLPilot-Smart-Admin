from db import get_conn


def query_products(name=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if name:
                cur.execute(
                    "SELECT id, name, price, stock, last_update "
                    "FROM product_lists WHERE name LIKE %s ORDER BY id",
                    (f"%{name}%",),
                )
            else:
                cur.execute(
                    "SELECT id, name, price, stock, last_update "
                    "FROM product_lists ORDER BY id"
                )
            return cur.fetchall()
    finally:
        conn.close()
def get_by_name(name):
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
            cur.execute(
                "INSERT INTO product_lists (name, price, stock) "
                "VALUES (%s, %s, %s)",
                (name, price, stock),
            )
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
def update_product(name, fields):
    if not fields:
        return 0
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join(f"{k}=%s" for k in fields)
            sql = f"UPDATE product_lists SET {set_clause} WHERE name=%s"
            cur.execute(sql, (*fields.values(), name))
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
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