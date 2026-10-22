from dbutils.pooled_db import PooledDB
import pymysql
from config import Config
from contextlib import AbstractContextManager


POOL = PooledDB(
    creator=pymysql,
    maxconnections=10,
    mincached=2,
    maxcached=5,
    blocking=True,
    ping=1,
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD,
    database=Config.DB_NAME,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
)


def get_conn():
    return POOL.connection()

class Transaction(AbstractContextManager):
    """
    事务上下文管理器。

        with Transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
                cur.execute(...)
        # 正常退出 -> commit；抛异常 -> rollback；无论如何 -> close（归还连接池）

    - 进入时：从连接池取一个连接
    - 正常退出（没抛异常）：commit
    - 抛异常：rollback，然后把异常继续往上抛
    - 无论如何：在 finally 里 close()，把连接还给池子
    """

    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = get_conn()
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.conn is not None:
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
        finally:
            if self.conn is not None:
                self.conn.close()
        return False   # 不吞异常，让它继续往上抛