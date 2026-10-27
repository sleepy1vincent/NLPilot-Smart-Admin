
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_conn
from services import enrich_services
import dao.product_dao as product_dao
import services.rag_services as rag_services

def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM product_lists "
                        "WHERE description IS NULL OR description = ''")
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("所有商品都已有描述 ✅")
        return

    print(f"待补标 {len(rows)} 个")
    for r in rows:
        e = enrich_services.tag(r["name"])
        if not e:
            print(f"  ✗ {r['name']} 打标失败")
            continue

        product_dao.save_enrichment(
            r["id"],
            e.get("category") or "",
            ",".join(e.get("tags") or []),
            e.get("description") or "",
        )

        row = product_dao.get_by_ids([r["id"]])
        if row:
            try:
                rag_services.upsert_product(row[0])
            except Exception as ex:
                print(f"    [RAG] 同步失败: {ex}")

        print(f"  ✓ {r['name']} → {e.get('category')} | {(e.get('description') or '')[:28]}")


if __name__ == "__main__":
    main()