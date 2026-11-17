"""对话记录 DAO。

表结构（已有，未改动）
=====================
    conversations(id, last_update, created_at)
    messages(id, belong_id, content, role enum('ai','user'), last_update)

返回协议
========
    create()                    → int            新会话 id
    add_message(conv_id, ...)   → None           只写库，无返回
    raw_messages(conv_id)       → list[{id, role, content, at}]
    history(conv_id, turns)     → list[{role, content}]    role 为 user / assistant
    list_conversations(limit)   → list[{id, title, count, last_update}]
    get_conversation(conv_id)   → dict | None    {id, last_update, messages:[...]}
    clear_messages(conv_id)     → int            删除的消息条数
    delete(conv_id)             → int            影响行数（0 = 会话不存在）

设计说明
--------
    1. **不存模型原文**。存的是"用户看到的那句话"：
       业务工具 → 存工具返回的 message（事实）
       clarify/refuse → 存渲染后的模板文案
       这样历史回放和当时看到的一致，也不会把模型编造的内容落库。

    2. **title 不落库**，由首条 user 消息截断生成（避免改表结构）。

    3. 历史转成 ollama 的 messages 格式时，role 的 'ai' 映射成 'assistant'。
"""
from db import get_conn, Transaction

TITLE_LEN = 24

# 动作日志表（启动时自动补齐，不用手动跑 SQL）
_ACTION_DDL = """
CREATE TABLE IF NOT EXISTS action_logs (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  belong_id  INT NOT NULL,
  step       INT NOT NULL DEFAULT 0,
  tool       VARCHAR(64) NOT NULL,
  args       TEXT NULL,
  ok         TINYINT(1) NULL,
  skipped    VARCHAR(128) NULL,
  summary    VARCHAR(500) NULL,
  detail     MEDIUMTEXT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_belong (belong_id),
  CONSTRAINT fk_action_conv FOREIGN KEY (belong_id)
      REFERENCES conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_table() -> None:
    """确保 action_logs 存在（幂等）。旧库不手动迁移也不会报错。"""
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(_ACTION_DDL)


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
            cur.execute("DELETE FROM action_logs WHERE belong_id = %s", (conv_id,))
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


def add_actions(conv_id: int, steps: list) -> None:
    """把一轮对话的 steps 落库（右侧日志的历史来源）。

    存什么：工具名 / 参数 / ok / 被跳过原因 / 结果摘要 / 原始返回（截断）。
    摘要和 detail 都存，前端展示时不用重算。
    """
    if not steps:
        return
    with Transaction() as conn:
        with conn.cursor() as cur:
            for s in steps:
                tool = (s or {}).get("tool")
                if not tool:
                    continue
                detail = None
                if s.get("result") is not None:
                    try:
                        import json as _json
                        detail = _json.dumps(s["result"], ensure_ascii=False)[:4000]
                    except Exception:
                        detail = None
                cur.execute(
                    "INSERT INTO action_logs "
                    "(belong_id, step, tool, args, ok, skipped, summary, detail) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (conv_id, int(s.get("step") or 0), tool,
                     _json_dumps(s.get("args")), 1 if s.get("ok") else 0,
                     s.get("skipped"), _summary_of(s.get("result")), detail),
                )


def raw_actions(conv_id: int, limit: int = 200) -> list:
    """按时间正序取动作日志。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT step, tool, args, ok, skipped, summary, detail, created_at "
                "FROM action_logs WHERE belong_id = %s ORDER BY id ASC LIMIT %s",
                (conv_id, limit),
            )
            rows = cur.fetchall()
    return [
        {"step": r["step"], "tool": r["tool"], "args": r["args"],
         "ok": bool(r["ok"]), "skipped": r["skipped"],
         "summary": r["summary"], "detail": r["detail"],
         "at": str(r["created_at"])}
        for r in rows
    ]


def _json_dumps(v) -> str | None:
    import json as _json
    try:
        return _json.dumps(v, ensure_ascii=False) if v is not None else None
    except Exception:
        return None


def _summary_of(r) -> str | None:
    """把工具返回值压成一行摘要（与前端 _summarize 同口径）。"""
    if not isinstance(r, dict):
        return None
    d = r.get("data")
    if isinstance(d, list):
        if not d:
            return r.get("message") or "0 条"
        names = [x.get("name") or x.get("product_name") or ""
                 for x in d[:3] if isinstance(x, dict)]
        names = [n for n in names if n]
        return f"{len(d)} 条" + (f"：{'、'.join(names)}" if names else "")
    if isinstance(d, dict):
        if "id" in d:
            return f"新增 id={d['id']}"
        if "affected" in d:
            return f"影响 {d['affected']} 行"
    return r.get("message") or "ok"


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
            "messages": raw_messages(conv_id),
            "logs": raw_actions(conv_id)}


def delete(conv_id: int) -> int:
    """删除会话（messages 靠外键级联删除）。"""
    with Transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))
            return cur.rowcount
