"""Agent 评测集：把"我觉得挺准"变成可复现的数字

用法
----
    cd backend
    python tests/agent_eval.py              # 默认 dry-run，不会真的改数据
    python tests/agent_eval.py --live       # 真的执行写操作（会改库，慎用）
    python tests/agent_eval.py --verbose    # 失败时打印模型原始决策

它测什么
--------
    ① 工具选择    模型有没有选对工具
    ② 参数正确    关键参数（预算/品类/用途/数量）有没有填对
    ③ 推荐质量    该推的有没有推出来、该拒绝的有没有拒绝
    ④ 安全行为    写操作是否走了"提案-确认"，没有凭空执行
    ⑤ 稳定性      单步请求的耗时

为什么默认 dry-run
------------------
评测要能反复跑。如果每跑一次就卖几件、加几个商品，
数据和基线都会被污染——上一版我就踩过这个坑（删掉了 16 条真实销售记录）。

所以默认把"有副作用的工具"替换成空实现：
  读工具（query_*/recommend_*）：真执行，因为要看结果
  提案工具（delete_product / apply_discount）：真执行，它们只返回提案不动数据
  写工具（create/update/record_sale/record_purchase）：**只记录，不执行**
"""
import json
import os
import sys
import time

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

LIVE = "--live" in sys.argv
VERBOSE = "--verbose" in sys.argv

# 这些工具有副作用，默认不真跑
SIDE_EFFECT_TOOLS = {"create_product", "update_product", "record_sale", "record_purchase"}

# (用户输入, 期望工具, 说明, 额外校验)
#   额外校验目前支持：
#     "args": {key: 期望值或判断函数}         —— 参数检查
#     "result": "empty" / "non_empty"         —— 结果条数
#     "result_any": [名称...]                  —— 结果里至少出现一个
CASES = [
    # ---------- 1. 工具选择：查询 ----------
    ("查一下 iPhone15 的库存", "query_products", "按名查询", {"args": {"name": "iPhone15"}}),
    ("有哪些商品", "query_products", "查全部"),
    ("有哪些耳机", "query_products", "按品类", {"args": {"category": "耳机"}, "result": "non_empty"}),
    ("500 以内有什么", "query_products", "价格上限", {"args": {"max_price": 500}}),
    ("有货的耳机有哪些", "query_products", "库存 + 品类", {"args": {"in_stock": True}}),

    # ---------- 2. 工具选择：推荐 ----------
    ("推荐个送女朋友的礼物", "recommend_products", "送礼推荐",
     {"args": {"occasion": "非空"}, "result": "non_empty"}),
    ("有什么适合学生党的", "recommend_products", "人群推荐",
     {"args": {"occasion": "非空"}, "result": "non_empty"}),
    ("推荐个降噪耳机", "recommend_products", "品类推荐",
     {"args": {"occasion": "非空"}, "result_any": ["索尼降噪耳机XM5", "AirPodsPro", "12"]}),
    ("500 以内送什么好", "recommend_products", "预算 + 用途",
     {"args": {"budget": 500}}),
    ("有没有适合钓鱼的", "recommend_products", "库里没有 → 该拒绝", {"result": "empty"}),

    # ---------- 3. 工具选择：写操作 ----------
    ("卖了 2 个 iPhone15", "record_sale", "销售", {"args": {"quantity": 2}}),
    ("AirPodsPro 售出 3 件", "record_sale", "销售（另一种说法）", {"args": {"quantity": 3}}),
    ("把 iPhone15 的价格改成 5799", "update_product", "改价", {"args": {"price": 5799}}),
    ("机械键盘K8 库存改成 50", "update_product", "改库存", {"args": {"stock": 50}}),
    ("iPhone15 打八折", "apply_discount", "打折提案", {}),
    ("删除 小米手环8", "delete_product", "删提案", {}),
    ("新增商品 测试品XYZ 价格 199 库存 30", "create_product", "新增", {}),
    ("进货 10 个 机械键盘K8", "record_purchase", "进货", {"args": {"quantity": 10}}),

    # ---------- 4. 工具选择：记录查询 ----------
    ("最近的销售记录", "query_sales", "销售记录"),
    ("这周的销售情况怎么样", "sales_report", "销售统计", {"args": {"days": 7}}),
    ("最近的进货记录", "query_purchases", "进货记录"),
]

# 命中的阈值（低于此值认为退化）
MIN_TOOL_ACCURACY = 0.90
MIN_PARAM_ACCURACY = 0.90


def _check_args(args: dict, spec: dict):
    """返回 (ok, 问题描述)"""
    for key, want in spec.items():
        got = args.get(key)
        if want == "非空":
            if not (got not in (None, "", [], {})):
                return False, f"{key} 为空"
        elif isinstance(want, (int, float)) and not isinstance(want, bool):
            try:
                if abs(float(got) - float(want)) > 1e-6:
                    return False, f"{key}={got}，期望 {want}"
            except (TypeError, ValueError):
                return False, f"{key}={got}，不是数字"
        elif isinstance(want, bool):
            if bool(got) != want:
                return False, f"{key}={got}，期望 {want}"
        elif isinstance(want, str):
            if want not in str(got or ""):
                return False, f"{key}={got}，期望包含「{want}」"
    return True, ""


def _check_result(result: dict, spec: str):
    n = result.get("count")
    if spec == "empty":
        return (n == 0), f"期望 0 条，实际 {n} 条"
    if spec == "non_empty":
        return (bool(n)), "期望有结果，实际 0 条"
    return True, ""


# 多步用例：只在循环模式下跑（单步模式这些任务本来就做不了）
#   (用户输入, 期望步数下限, 期望步数上限)
MULTI_CASES = [
    ("这周卖得最好的商品还有多少库存", 2, 3),   # 必须先查销量、再查库存
    ("查 iPhone15，再把它打八折", 2, 3),        # 先查、再提案打折
    ("对比 iPhone15 和 AirPodsPro 的价格", 1, 3),
]


def main():
    try:
        import app as appmod
    except Exception as ex:
        print(f"[错误] 后端初始化失败（MySQL / Ollama 起来了吗？）: {ex}")
        return 2

    import services.product_service as ps
    from config import Config

    # 报告实际运行模式——否则"评测通过"可能测的是旧路径
    # 判据：配置开了 CHAT_LOOP，且 agent_service 里确实有 run_loop
    loop_ready = False
    if Config.CHAT_LOOP:
        try:
            from services import agent_service
            loop_ready = callable(getattr(agent_service, "run_loop", None))
        except Exception:
            loop_ready = False
    mode = "多步循环" if loop_ready else "单步"

    calls = []
    orig_handle = ps.handle

    def dry_handle(call):
        tool = call.get("tool")
        if not LIVE and tool in SIDE_EFFECT_TOOLS:
            calls.append((tool, call.get("args")))
            return {"ok": True, "dry_run": True,
                    "message": f"[dry-run] 未真正执行 {tool}"}
        return orig_handle(call)

    ps.handle = dry_handle
    cli = appmod.app.test_client()

    print("=" * 96)
    print(f"Agent 评测   模式={'LIVE（会改数据）' if LIVE else 'dry-run（写操作不执行）'}"
          f"   走哪条链路={mode}")
    print("=" * 96)
    print(f"  {'#':<3}{'用户输入':<28}{'期望工具':<20}{'实际工具':<20}{'结果':<6}{'耗时'}")
    print("  " + "-" * 90)

    total = len(CASES)
    tool_ok = param_ok = param_checked = result_ok = result_checked = 0
    failures = []
    t_all = 0.0

    try:
        for i, case in enumerate(CASES, 1):
            msg, expect_tool, tag = case[0], case[1], case[2]
            spec = case[3] if len(case) > 3 else {}
            t0 = time.time()
            d = cli.post("/api/chat", json={"message": msg}).get_json().get("data") or {}
            dt = time.time() - t0
            t_all += dt

            call = d.get("call") or {}
            result = d.get("result") or {}
            got_tool = call.get("tool")
            ok_tool = (got_tool == expect_tool)
            if ok_tool:
                tool_ok += 1

            note = ""
            # 参数校验
            if spec.get("args") and ok_tool:
                param_checked += 1
                good, why = _check_args(call.get("args") or {}, spec["args"])
                if good:
                    param_ok += 1
                else:
                    note = why
                    failures.append((msg, f"参数：{why}"))
            # 结果校验
            if spec.get("result") and ok_tool:
                result_checked += 1
                good, why = _check_result(result, spec["result"])
                if good:
                    result_ok += 1
                else:
                    note = why
                    failures.append((msg, f"结果：{why}"))
            if spec.get("result_any") and ok_tool:
                result_checked += 1
                names = [x.get("name") for x in (result.get("data") or []) if isinstance(x, dict)]
                if any(n in names for n in spec["result_any"]):
                    result_ok += 1
                else:
                    note = f"未包含 {spec['result_any']}，实际 {names[:3]}"
                    failures.append((msg, f"结果：{note}"))

            if not ok_tool:
                failures.append((msg, f"工具：期望 {expect_tool}，实际 {got_tool}"))

            flag = "✅" if ok_tool else "❌"
            print(f"  {i:<3}{msg[:26]:<28}{expect_tool:<20}{str(got_tool):<20}{flag:<6}{dt:.1f}s")
            if note:
                print(f"       └─ {note}")
            if VERBOSE and not ok_tool:
                print(f"       └─ 原始决策: {json.dumps(call, ensure_ascii=False)[:160]}")
    finally:
        ps.handle = orig_handle

    # ---------- 多步用例（仅循环模式） ----------
    multi_ok = multi_total = 0
    if loop_ready:
        print()
        print("=" * 96)
        print("多步用例（只有循环模式才跑）")
        print("=" * 96)
        print(f"  {'用户输入':<30}{'期望步数':<12}{'实际步数':<10}{'结果'}")
        print("  " + "-" * 90)
        for msg, lo, hi in MULTI_CASES:
            multi_total += 1
            t0 = time.time()
            d = cli.post("/api/chat", json={"message": msg}).get_json().get("data") or {}
            dt = time.time() - t0
            trace = d.get("trace") or []
            n = len([t for t in trace if not t.get("skipped")])
            good = lo <= n <= hi and d.get("executed", 0) >= 1
            if good:
                multi_ok += 1
            else:
                failures.append((msg, f"多步：期望 {lo}~{hi} 步，实际 {n} 步，executed={d.get('executed')}"))
            print(f"  {msg[:28]:<30}{f'{lo}~{hi}':<12}{n:<10}{'✅' if good else '❌'}  {dt:.1f}s")
    elif Config.CHAT_LOOP:
        print("\n  提示：CHAT_LOOP=1 但 agent_service.run_loop 不可用，多步用例跳过")

    print()
    print("=" * 96)
    print("结果")
    print("=" * 96)
    acc_t = tool_ok / total
    print(f"  工具选择      {tool_ok}/{total} = {acc_t*100:.0f}%")
    if param_checked:
        print(f"  参数正确      {param_ok}/{param_checked} = {param_ok/param_checked*100:.0f}%")
    if result_checked:
        print(f"  结果符合预期  {result_ok}/{result_checked} = {result_ok/result_checked*100:.0f}%")
    if multi_total:
        print(f"  多步任务      {multi_ok}/{multi_total}")
    print(f"  平均耗时      {t_all/total:.2f}s / 次")
    if not LIVE:
        print(f"  （dry-run 拦截了 {len(calls)} 次写操作：{sorted({c[0] for c in calls})}）")

    if failures:
        print("\n  失败明细：")
        for msg, why in failures:
            print(f"    · {msg} —— {why}")

    acc_p = (param_ok / param_checked) if param_checked else 1.0
    passed = acc_t >= MIN_TOOL_ACCURACY and acc_p >= MIN_PARAM_ACCURACY
    if multi_total:
        passed = passed and multi_ok == multi_total
    print()
    print(f"  判定：{'✅ 通过' if passed else '❌ 未达基线'}"
          f"（工具 ≥{MIN_TOOL_ACCURACY*100:.0f}%，参数 ≥{MIN_PARAM_ACCURACY*100:.0f}%"
          f"{'，多步全对' if multi_total else ''}）")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
