import pymysql
import queue

class PooledConnection:
    def __init__(self,conn,pool):
        self._conn=conn
        self._pool=pool
    def cursor(self,*args,**kwargs):
        return self._conn.cursor(*args,**kwargs)
    def commit(self):
        return self._conn.commit()
    def rollback(self):
        return self._conn.rollback()
    def close(self):
        return self._pool.release(self._conn)

class MyPool:
    def __init__(self,size=3,**conn_kwargs):
        self._pool=queue.Queue(maxsize=size)
        self._conn_kwargs = conn_kwargs
        for x in range(size):
            raw=pymysql.connect(**conn_kwargs)
            self._pool.put(raw)
    def get_conn(self,timeout=5):
            try:
                raw = self._pool.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError("连接池取连接超时")
            try:
                raw.ping(reconnect=True)
            except Exception:
                raw =pymysql.connect(**self._conn_kwargs)
            return PooledConnection(raw,self)
    def release(self,conn):
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            conn.close()

# 测试代码
if __name__=='__main__':
    pool=MyPool(5, host='127.0.0.1',
        user='root',
        password='你的密码',
        database='nlpilot',
        charset='utf8mb4',)
    conn=pool.get_conn()
    pool.release(conn)