from db import get_conn

def record_purchase(product_name:str,quantity:int,unit_price:float)->int:
    """记录一笔进货"""
    total=round(quantity*unit_price,2)
    conn=get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into purchases(product_name,quantity,unit_price,total)"
                "values(%s,%s,%s,%s)",
                (product_name,quantity,unit_price,total),
            )
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
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

