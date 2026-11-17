"""一条命令启动整个系统：后端 + 前端（已构建）+ 自动打开浏览器。

用法：
    python run.py

它做三件事：
    1. 检查前端是否已构建（没构建就提示一条命令）
    2. 起后端（同时托管前端静态文件）
    3. 2 秒后自动打开浏览器

只开一个进程、一个网址 —— 演示/答辩用这个，不要再用 ng serve。
"""
import os
import sys
import threading
import time
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "backend"))

from config import Config
from app import app, _has_dist, _DIST


def _open_browser():
    time.sleep(2.0)
    url = f"http://127.0.0.1:{Config.PORT}"
    print(f"\n  打开浏览器：{url}\n")
    webbrowser.open(url)


if __name__ == "__main__":
    print("=" * 60)
    print("NLPilot 启动中")
    print("=" * 60)
    if _has_dist():
        print(f"  前端：已构建（{_DIST}）")
    else:
        print("  前端：未构建 ⚠️")
        print("        请先执行：cd frontend && npm run build")
        print("        （现在只会有接口，没有界面）")
    print(f"  后端：http://127.0.0.1:{Config.PORT}   （同时托管前端）")
    print("  停止：Ctrl+C")
    print("=" * 60)

    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
