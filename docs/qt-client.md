# Qt 客户端对接指南

面向：用 Qt 写一个桌面客户端，通过 HTTP 调 NLPilot 后端。

**核心原则：Qt 只做"壳"，不碰数据库、不碰大模型。**
所有业务走 `http://127.0.0.1:5001/api`，和 Web 前端用的是同一套接口。

---

## 一、技术选型

| 选择 | 推荐 | 理由 |
|---|---|---|
| 绑定 | **PySide6** | 官方维护、LGPL（可闭源商用）；PyQt6 是 GPL/商业双许可 |
| 网络 | `QNetworkAccessManager` | 原生异步，不阻塞 UI 线程 |
| 渲染 | `QTextBrowser` + HTML | 卡片/气泡用受限 HTML 就够，不必上 QML |
| 打包 | PyInstaller | `--onefile --windowed` |

> 不建议用 `requests` 直接在主线程发请求——一次对话要 2~12 秒，界面会卡死。
> 要么用 `QNetworkAccessManager`，要么把 `requests` 丢进 `QThread`。

---

## 二、接口契约

### 发消息

```
POST /api/chat
Content-Type: application/json

{"message": "查一下 iPhone15 的库存", "conversation_id": 12}
```

`conversation_id` 省略 = 新建会话；**返回值里会带回 `conversation_id`，下次带上即可续聊。**

响应：

```json
{
  "code": 200,
  "message": "用户看到的那句话",
  "data": {
    "conversation_id": 12,
    "call":     {"tool": "query_products", "args": {...}},
    "result":   {"ok": true, "count": 1, "data": [...], "is_rag": false},
    "reply":    "",
    "executed": 1,
    "trace":    [{"step": 1, "tool": "query_products", "ok": true}]
  }
}
```

**怎么渲染（照抄 Web 前端的规则）：**

| 字段 | 含义 | 客户端该做什么 |
|---|---|---|
| `executed >= 1` 且 `result.data` 是数组 | 查询/推荐结果 | 渲染成"结果卡片"，内容取 `result`，**不要用 `reply` 覆盖** |
| `executed >= 1` 且 `reply` 非空 | 多步总结 | 卡片下面再显示一段文字，标注"依据上方结果" |
| `result.need_confirm` | 需要确认（删除/打折） | `QMessageBox` 弹确认 → 调 `/api/chat/confirm` |
| `result.need_clarify` | 商品名不唯一/缺参数 | 直接把 `result.message` 显示给用户 |
| `executed == 0` 且 `reply` 非空 | 模板话术（闲聊/拒绝/兜底） | 用灰色气泡显示 |

> `reply` 永远是**后端模板**，不是模型原文——所以可以安全地直接显示。

### 确认操作

```
POST /api/chat/confirm
{"action": "delete", "target": "小米手环8", "data": ""}
{"action": "discount", "target": "iPhone15", "data": 4639.2}
```

### 会话列表 / 详情

```
GET    /api/conversations          → [{"id","title","count","last_update"}]
GET    /api/conversations/<id>     → {"id","messages":[{"role","content","at"}]}
DELETE /api/conversations/<id>
```

历史消息只有 `role` + `content`（存的就是用户当时看到的话），
所以回放时**一律按普通气泡渲染**即可。

---

## 三、最小可用客户端（约 120 行）

```python
import json
import sys

from PySide6.QtCore import QUrl, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextBrowser, QLineEdit, QPushButton, QMessageBox,
)

BASE = "http://127.0.0.1:5001/api"


class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NLPilot 客户端")
        self.resize(880, 680)
        self.conv_id = None          # 会话 id，后端返回后保存
        self.net = QNetworkAccessManager(self)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)

        self.input = QLineEdit()
        self.input.setPlaceholderText("例如：查一下 iPhone15 的库存")
        self.input.returnPressed.connect(self.send)

        self.btn = QPushButton("发送")
        self.btn.clicked.connect(self.send)

        row = QHBoxLayout()
        row.addWidget(self.input)
        row.addWidget(self.btn)

        box = QVBoxLayout(self)
        box.addWidget(self.view)
        box.addLayout(row)

    # ---------------------------------------------------------------- 发送
    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.btn.setEnabled(False)
        self._append("user", text)

        body = json.dumps({"message": text, "conversation_id": self.conv_id})
        req = QNetworkRequest(QUrl(f"{BASE}/chat"))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                      "application/json; charset=utf-8")
        reply = self.net.post(req, body.encode("utf-8"))
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply: QNetworkReply):
        self.btn.setEnabled(True)
        raw = bytes(reply.readAll()).decode("utf-8", "replace")
        reply.deleteLater()
        try:
            payload = json.loads(raw)
        except Exception:
            self._append("system", f"响应解析失败：{raw[:200]}")
            return

        if reply.error() != QNetworkReply.NetworkError.NoError and payload.get("code") != 200:
            self._append("system", payload.get("message") or "请求失败")
            return

        data = payload.get("data") or {}
        if data.get("conversation_id"):
            self.conv_id = data["conversation_id"]

        result = data.get("result") or {}

        # ① 需要确认
        if result.get("need_confirm"):
            ok = QMessageBox.question(
                self, "确认操作", result.get("message", "确认执行？")
            ) == QMessageBox.StandardButton.Yes
            if ok:
                self._confirm(result.get("action"), result.get("target"),
                              result.get("data", ""))
            else:
                self._append("system", "已取消")
            return

        # ② 需要澄清
        if result.get("need_clarify"):
            self._append("system", result.get("message", ""))
            return

        # ③ 有事实：渲染结果卡片
        if data.get("executed"):
            self._append("card", self._format_result(result),
                         rag=bool(result.get("is_rag")),
                         steps=len(data.get("trace") or []))
            summary = (data.get("reply") or "").strip()
            if summary:
                self._append("summary", summary)
            return

        # ④ 模板话术
        self._append("system", data.get("reply") or payload.get("message") or "（无回复）")

    def _confirm(self, action, target, value):
        body = json.dumps({"action": action, "target": target, "data": value})
        req = QNetworkRequest(QUrl(f"{BASE}/chat/confirm"))
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                      "application/json; charset=utf-8")
        reply = self.net.post(req, body.encode("utf-8"))
        reply.finished.connect(lambda: (
            self._append("system", json.loads(bytes(reply.readAll()).decode("utf-8")).get("message", "")),
            reply.deleteLater(),
        ))

    # ---------------------------------------------------------------- 渲染
    def _format_result(self, result) -> str:
        rows = result.get("data")
        if isinstance(rows, list):
            if not rows:
                return result.get("message") or "未找到数据"
            lines = []
            for it in rows:
                if it.get("name") is not None and it.get("price") is not None:
                    lines.append(f"· {it['name']}　¥{it['price']}　库存 {it.get('stock', '-')}")
                elif it.get("product_name"):
                    lines.append(f"· {it['product_name']}　×{it.get('quantity', '-')}")
                else:
                    lines.append(f"· {it}")
            return f"共 {len(rows)} 条\n" + "\n".join(lines)
        return result.get("message") or ""

    def _append(self, kind: str, text: str, rag=False, steps=0):
        esc = (text or "").replace("&", "&amp;").replace("<", "&lt;")
        if kind == "user":
            html = f'<div align="right"><span style="background:#2563eb;color:#fff;padding:8px 12px;border-radius:12px">{esc}</span></div>'
        elif kind == "card":
            color = "#6d3fc0" if rag else "#15803d"
            label = "语义召回" if rag else "数据库"
            step = f"　{steps} 步" if steps > 1 else ""
            html = (f'<div style="border:1px solid #e3e8ef;border-radius:12px;padding:10px">'
                    f'<div style="color:{color};font-size:11px">{label} · 操作结果{step}</div>'
                    f'<pre style="font-family:inherit;white-space:pre-wrap;margin:6px 0 0">{esc}</pre></div>')
        elif kind == "summary":
            html = f'<div style="background:#eef4ff;border:1px solid #dbe7fd;padding:8px 12px;border-radius:12px">{esc}</div>'
        else:
            html = f'<div align="left"><span style="background:#f3f5f9;padding:8px 12px;border-radius:12px">{esc}</span></div>'
        self.view.append(html)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ChatWindow()
    w.show()
    sys.exit(app.exec())
```

---

## 四、坑（都是实际会遇到的）

| 坑 | 现象 | 对策 |
|---|---|---|
| **在主线程同步请求** | 界面卡 5~12 秒 | 用 `QNetworkAccessManager` 或 `QThread` |
| 编码 | 中文变乱码 | 请求体 `encode("utf-8")`、响应 `decode("utf-8")`、头里带 `charset=utf-8` |
| 超时 | 首字很慢（模型冷启动） | 超时设 60s 以上，并显示"处理中" |
| 用 `reply` 覆盖卡片 | 数字对不上 | 有 `executed` 就只渲染 `result` |
| 忘了带 `conversation_id` | 每次都是新对话，多轮指代失效 | 首次响应后保存，之后每次带上 |
| 后端没启动 | 连接被拒 | 启动前检查 `/api/health`，给出提示 |
| CORS | 不适用 | Qt 不是浏览器，不受 CORS 限制 |

---

## 五、可选的加分项

1. **多步进度**：`trace` 里每一步都能实时展示（"第 1 步 查询中…"）——
   要做到实时，需要后端把 `/api/chat` 改成 SSE 流式返回（当前未实现）。
2. **会话侧栏**：`GET /api/conversations` 已经能列出历史，直接用 `QListWidget`。
3. **商品表格**：`GET /api/products` 返回全量商品，可用 `QTableView` 展示。
4. **快捷键**：`Ctrl+Enter` 发送、`Esc` 取消正在进行的请求（`reply.abort()`）。

---

## 六、和 Web 前端的关系

```
            ┌────────────────┐
            │  Flask 后端     │
            └───────┬────────┘
        ┌───────────┴───────────┐
   Angular Web             Qt 客户端
   （浏览器）               （桌面）
```

**两者是平级的客户端，共享同一套 API。**
这也是为什么"业务全在后端"很重要——新增一个客户端不用重写逻辑。
