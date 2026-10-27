"""补充演示商品数据（幂等：已存在的商品会跳过）

用法：
    cd backend && python scripts/seed_demo.py
    cd backend && python scripts/seed_demo.py --with-sales    # 额外生成销售记录

设计说明
--------
1. 商品名、品类、标签、描述**手写**，不走 LLM 打标——演示数据要可控、可解释。
2. 每条描述都刻意带上"场景/人群"词（办公、出差、送礼、学生、运动、旅行），
   这样语义检索和推荐才有东西可召回。
3. 插完立即同步向量库，避免"SQL 有、索引没有"的幽灵/漏召回。
4. 全程幂等：同名商品跳过，可以反复执行。
"""
import os
import sys

# 允许从 backend/ 或仓库根目录运行
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import dao.product_dao as pd
import services.rag_services as rag

# (名称, 价格, 库存, 品类, 标签, 描述)
SEED = [
    # ---------- 耳机 ----------
    ("索尼降噪耳机XM5", 2499, 25, "耳机", "降噪,通勤,旅行,头戴",
     "头戴式主动降噪耳机，地铁通勤和长途飞行都能安静听歌。"),
    ("舒尔入耳式耳机SE215", 799, 28, "耳机", "听歌,隔音,专业,有线",
     "入耳式监听耳机，隔音效果好，听歌细节丰富。"),
    # ---------- 音箱 ----------
    ("漫步者蓝牙音箱M25", 299, 60, "音箱", "聚会,户外,便携,送礼",
     "便携蓝牙音箱，户外聚会和露营都能带动气氛，小巧适合送礼。"),
    # ---------- 存储 ----------
    ("三星移动固态硬盘T7", 699, 40, "存储", "备份,办公,便携,高速",
     "1TB 移动固态硬盘，读写快，出差办公备份资料很方便。"),
    # ---------- 键鼠 ----------
    ("罗技无线鼠标MX3", 699, 30, "鼠标", "办公,静音,无线,人体工学",
     "人体工学无线鼠标，长时间办公手腕不累，点击安静不吵人。"),
    ("樱桃机械键盘MX8", 899, 20, "键盘", "办公,游戏,机械,背光",
     "机械键盘，办公和游戏两用，背光亮度可调。"),
    ("罗技蓝牙键盘K380", 229, 90, "键盘", "学生,办公,便携,蓝牙",
     "薄膜蓝牙键盘，可同时连三台设备，学生带去图书馆很方便。"),
    # ---------- 充电 ----------
    ("安克氮化镓充电器65W", 199, 120, "充电宝", "出差,便携,快充,办公",
     "65W 氮化镓充电器，一个头同时给笔记本和手机快充，出差必备。"),
    ("小米移动电源3", 89, 200, "充电宝", "便携,旅行,学生,应急",
     "10000mAh 轻薄移动电源，学生上课和日常通勤随身带着不占地方。"),
    # ---------- 穿戴 ----------
    ("华为手表GT4", 1488, 35, "穿戴", "运动,健康,送礼,长续航",
     "智能手表，心率血氧监测，运动记录，包装体面适合送礼。"),
    # ---------- 平板 / 电脑 ----------
    ("小米平板6", 1999, 45, "平板", "追剧,学生,学习,轻薄",
     "11 英寸平板，追剧和上网课都合适，学生党首选。"),
    ("联想小新Pro14", 5299, 18, "电脑", "办公,轻薄,学生,高效",
     "14 英寸轻薄笔记本，办公和写论文都够用，续航长。"),
    # ---------- 显示器 ----------
    ("戴尔27寸4K显示器", 2299, 20, "显示器", "办公,设计,高清,护眼",
     "27 英寸 4K 显示器，修图和写代码都清晰，低蓝光护眼。"),
    # ---------- 配件 ----------
    ("绿联Type-C扩展坞", 159, 150, "配件", "办公,便携,扩展,出差",
     "七合一扩展坞，笔记本接显示器、U 盘、网线一步到位。"),
    # ---------- 摄影 ----------
    ("大疆手机云台", 599, 22, "摄影", "拍摄,旅行,Vlog,送礼",
     "手机云台，旅行拍 Vlog 稳定不抖，送礼有面子。"),
    ("罗技高清摄像头C920", 399, 30, "摄影", "办公,会议,网课,高清",
     "1080P 高清摄像头，远程会议和网课都清晰。"),
]

# 销售历史：(商品名, 数量, 单价, 几天前)
SEED_SALES = [
    ("iPhone15", 2, 5799.00, 1),
    ("AirPodsPro", 3, 1899.00, 2),
    ("小米移动电源3", 5, 89.00, 2),
    ("漫步者蓝牙音箱M25", 4, 299.00, 3),
    ("华为手表GT4", 2, 1488.00, 4),
    ("小米平板6", 3, 1999.00, 5),
    ("罗技无线鼠标MX3", 6, 699.00, 6),
    ("索尼降噪耳机XM5", 2, 2499.00, 8),
    ("绿联Type-C扩展坞", 8, 159.00, 9),
    ("樱桃机械键盘MX8", 3, 899.00, 11),
    ("大疆手机云台", 2, 599.00, 13),
    ("小米手环8", 6, 249.00, 15),
]


def main():
    with_sales = "--with-sales" in sys.argv

    print("=" * 78)
    print("补充演示数据")
    print("=" * 78)

    added, skipped = [], []
    for name, price, stock, cat, tags, desc in SEED:
        if pd.get_by_name(name):
            skipped.append(name)
            continue
        new_id = pd.insert_product(name, price, stock)
        pd.save_enrichment(new_id, cat, tags, desc)
        added.append((new_id, name, cat))

    print(f"\n  新增商品 {len(added)} 个，跳过已存在 {len(skipped)} 个")
    for i, name, cat in added:
        print(f"    #{i:<3} {name:<24} [{cat}]")

    # 同步向量库（关键：SQL 有、索引没有会导致召回不到）
    # 注意：这里同步**全部商品**而不是只同步新增的——
    # 只同步新增的话，一旦上次同步失败（例如 Ollama 没开），重跑也补不上。
    # upsert 是幂等的，多同步几次没有副作用。
    print("\n  同步向量库（全部商品）：")
    synced, failed = 0, []
    for row in pd.query_products():
        try:
            rag.upsert_product(row)
            synced += 1
        except Exception as ex:
            failed.append((row["name"], str(ex)[:60]))
    print(f"    成功 {synced} 条")
    if failed:
        print(f"    失败 {len(failed)} 条（多半是 Ollama 没启动）：")
        for name, err in failed[:3]:
            print(f"      {name}: {err}")
        print("    → 启动 Ollama 后重跑本脚本，或直接重启后端（启动时会全量重建索引）")

    if with_sales:
        print("\n  生成销售记录（同日同商品已存在则跳过）：")
        done, dup = 0, 0
        for name, qty, price, days in SEED_SALES:
            row = pd.get_by_name(name)
            if not row:
                print(f"    跳过（商品不存在）{name}")
                continue
            # 幂等：同商品、同一天已经有记录就不再插入
            with pd.get_conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) n FROM sales WHERE product_name=%s "
                        "AND DATE(sold_at)=DATE_SUB(CURDATE(), INTERVAL %s DAY)",
                        (name, days))
                    if cur.fetchone()["n"]:
                        dup += 1
                        continue
            if row["stock"] < qty:
                print(f"    跳过（库存不足 {row['stock']}<{qty}）{name}")
                continue
            from db import Transaction
            with Transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sales(product_name, quantity, unit_price, total, sold_at) "
                        "VALUES(%s,%s,%s,%s, DATE_SUB(NOW(), INTERVAL %s DAY))",
                        (name, qty, price, round(qty * price, 2), days))
                    cur.execute(
                        "UPDATE product_lists SET stock = stock - %s WHERE name = %s",
                        (qty, name))
            done += 1
            print(f"    {name} × {qty}  ¥{price}  ({days} 天前)")
        print(f"    新增 {done} 条，跳过重复 {dup} 条")

    with pd.get_conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM product_lists")
            n = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM sales")
            s = cur.fetchone()["n"]
    print(f"\n  当前：商品 {n} 个，销售 {s} 条，向量 {rag._get().count()} 条")
    print("  完成。重启后端会自动重建索引；不重启也已同步。")


if __name__ == "__main__":
    main()
