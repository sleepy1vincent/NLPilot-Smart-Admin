from db import get_conn

def record_purchase(product_name:str, quantity:int, unit_price:float,
                    conn=None, cursor=None, total=None)->int:
    """
    写入一条进货记录，返回自增 id。

    事务边界由调用方决定：
      - 都不传：自己开连接、自己 commit（适合"只写一条"的独立场景）
      - 传了 cursor：在调用方的事务游标上执行，【不 commit、不 close】
      - 传了 conn：用调用方的连接开游标，同样【不 commit、不 close】

    注意：传 cursor/conn 时，提交与回滚的责任在调用方。
    """
    if total is None:
        total = round(quantity * unit_price, 2)
    sql = ("insert into purchases(product_name,quantity,unit_price,total)"
           "values(%s,%s,%s,%s)")
    args = (product_name, quantity, unit_price, total)

    # 借用调用方的游标：同一个事务里的一条语句
    if cursor is not None:
        cursor.execute(sql, args)
        return cursor.lastrowid

    # 借用调用方的连接：不 commit，交给调用方
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid

    # 独立使用：自己管连接和事务
    own = get_conn()
    try:
        with own.cursor() as cur:
            cur.execute(sql, args)
            new_id = cur.lastrowid
        own.commit()
        return new_id
    except Exception:
        own.rollback()
        raise
    finally:
        own.close()
def get_purchase(product_name:str=None,days:int=None)->list:
    """查询进货记录"""
    conn=get_conn()
    try:
        with conn.cursor() as cur:
            sql="select * from purchases where 1=1"
            params=[]
            if product_name:
                sql+=" and product_name=%s"
                params.append(product_name)
            if days:
                sql+=" and purchased_at >=date_sub(now(),interval %s day)"
                params.append(days)
            sql+=" order by purchased_at DESC"
            cur.execute(sql,params)
            return cur.fetchall()
    finally:
        conn.close()
def total_purchased(product_name:str=None,days:int=None)->int:
    """统计总进货量"""
    conn=get_conn()
    try:
        with conn.cursor() as cur:
            sql="select coalesce(sum(quantity),0) as total from purchases where 1=1"
            params=[]
            if product_name:
                sql+=" and product_name=%s"
                params.append(product_name)
            if days:
                sql+=" and purchased_at>=date_sub(now(),interval %s day)"
                params.append(days)
            cur.execute(sql,params)
            row=cur.fetchone()
            return int(row["total"])
    except Exception:
        raise
    finally:
        conn.close()

