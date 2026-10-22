from flask import Flask
from flask_cors import CORS
from config import Config
from routes.product_routes import bp as product_bp
from routes.purchases_routes import bp as purchases_bp
from routes.chat_routes import bp as chat_bp
from routes.sales_routes import bp as sales_bp
from response import success
from dao import product_dao
from services import  rag_services
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(product_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(purchases_bp)

def _boot_check():
    """启动自检：同步索引 + 报告标签覆盖率。任何异常都不阻止启动。"""
    try:
        rows = product_dao.query_products()
        rag_services.init_product([{
            "id": r["id"], "name": r["name"], "category": r.get("category"),
            "tags": r.get("tags"), "description": r.get("description"),
        } for r in rows])

        missing = [r["name"] for r in rows if not (r.get("description") or "").strip()]
        total = len(rows)
        if missing:
            print(f"[自检] ⚠️ {len(missing)}/{total} 个商品缺描述，语义检索对它们无效：")
            for n in missing[:5]:
                print(f" - {n}" + (" …" if len(missing) > 5 else ""))
            print(f"   补全命令：cd backend && python scripts/auto_tag.py")
        else:
            print(f"[自检] ✅ {total}/{total} 个商品都有描述，语义检索完整")
    except Exception as e:
        print(f"[自检] RAG 初始化失败，降级为纯 SQL 模式: {e}")

with app.app_context():
    _boot_check()

@app.route("/api/health")
def health():
    stats = {"products": 0, "with_description": 0}
    try:
        rows = product_dao.query_products()
        stats["products"] = len(rows)
        stats["with_description"] = sum(
            1 for r in rows if (r.get("description") or "").strip())
    except Exception as e:
        stats["error"] = str(e)
    rag_stats = {"ok": False}
    try:
        col = rag_services._get()
        rag_stats = {"ok": True, "vectors": col.count()}
    except Exception as e:
        rag_stats["error"] = str(e)
    return success(data={"service": "NLPilot running",
                         "data_quality": stats, "rag": rag_stats})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)