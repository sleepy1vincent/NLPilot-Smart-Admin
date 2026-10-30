"""对话记录 DAO。

表结构（已有，未改动）
    conversations(id, last_update, created_at)
    messages(id, belong_id, content, role enum('ai','user'), last_update)

设计说明
--------
1. **不存模型原文**。存的是"用户看到的那句话"：
   业务工具 → 存工具返回的 message（事实）
   clarify/refuse → 存渲染后的模板文案
   这样历史回放和当时看到的一致，也不会把模型编造的内容落库。

2. **title 不落库**，由首条 user 消息截断生成（避免改表结构）。

3. 历史转成 ollama 的 messages 格式时，role 的 'ai' 要映射成 'assistant'。
"""
from db import get_conn, Transaction

TITLE_LEN = 24


def create() -> int:
    """新建一个会话，返回 id。

    注意：写操作必须走 Transaction()——get_conn() 只是借连接，
    退出 with 时不会 commit（autocommit=False），数据会丢。
    """
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO conversations () VALUES ()")
            return int(cur.lastrowid)


def clear_messages(conv_id: int) -> int:
    """清空某个会话的消息（保留会话本身）。

    用途：评测时每个用例都要"零历史"，否则上一题的上下文会干扰下一题
    （实测共用历史时，工具选择从 21/21 掉到 18/21）。
    """
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM messages WHERE belong_id = %s", (conv_id,))
            return cur.rowcount


def add_message(conv_id: int, role: str, content: str) -> None:
    """追加一条消息。role 只能是 'user' / 'ai'。"""
    if role not in ("user", "ai"):
        role = "ai"
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (belong_id, content, role) VALUES (%s, %s, %s)",
                (conv_id, content or "", role),
            )
            cur.execute(
                "UPDATE conversations SET last_update = CURRENT_TIMESTAMP WHERE id = %s",
                (conv_id,),
            )


def raw_messages(conv_id: int, limit: int = 200) -> list:
    """按时间正序取消息（给接口展示用）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content, role, last_update FROM messages "
                "WHERE belong_id = %s ORDER BY id ASC LIMIT %s",
                (conv_id, limit),
            )
            rows = cur.fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"],
         "at": str(r["last_update"])}
        for r in rows
    ]


def history(conv_id: int, turns: int = 6) -> list:
    """取最近若干条消息，转成 ollama 的 messages 格式（给模型当上下文）。"""
    rows = raw_messages(conv_id, limit=200)[-turns:]
    return [
        {"role": "assistant" if r["role"] == "ai" else "user",
         "content": r["content"]}
        for r in rows
    ]


def list_conversations(limit: int = 30) -> list:
    """会话列表：id + 标题（首条用户消息）+ 最后更新时间 + 消息数。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, last_update FROM conversations ORDER BY last_update DESC LIMIT %s",
                (limit,),
            )
            convs = cur.fetchall()
            if not convs:
                return []
            ids = [c["id"] for c in convs]
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"SELECT belong_id, content, role, id FROM messages "
                f"WHERE belong_id IN ({placeholders}) ORDER BY id ASC",
                ids,
            )
            rows = cur.fetchall()

    first_user, counts = {}, {}
    for r in rows:
        counts[r["belong_id"]] = counts.get(r["belong_id"], 0) + 1
        if r["role"] == "user" and r["belong_id"] not in first_user:
            first_user[r["belong_id"]] = r["content"]

    out = []
    for c in convs:
        title = (first_user.get(c["id"]) or "新对话").replace("\n", " ").strip()
        if len(title) > TITLE_LEN:
            title = title[:TITLE_LEN] + "…"
        out.append({
            "id": c["id"],
            "title": title,
            "count": counts.get(c["id"], 0),
            "last_update": str(c["last_update"]),
        })
    return out


def get_conversation(conv_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, last_update FROM conversations WHERE id = %s", (conv_id,))
            row = cur.fetchone()
    if not row:
        return None
    return {"id": row["id"], "last_update": str(row["last_update"]),
            "messages": raw_messages(conv_id)}


def delete(conv_id: int) -> int:
    """删除会话（messages 靠外键级联删除）。"""
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
            return cur.rowcount
