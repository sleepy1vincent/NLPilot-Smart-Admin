# NLPilot - 智能商品管理系统

> 自然语言驱动的商品管理。
> ⚠️ **实验性项目** —— 基于 7B 模型的 AI 工具调用，稳定性有限。

## ⚠️ 当前状态

- **版本**：v0.2.1
- **成熟度**：实验性 / Demo（核心链路已实测通过）
- **实测结果**（MySQL 8.0.46 + Ollama qwen2.5:7b）：

  | 指标 | 结果 |
  |---|---|
  | AI 工具选择准确率 | **17/17 = 100%** |
  | 幻觉（编造操作成功） | **0/17** |
  | 正常问答误伤 | **0/8** |
  | 参数校验（布尔/边界） | **9/9 正确** |
  | HTTP 状态码 | **6/6 正确** |
  | 前端单测 | **1 passed** |
  | 前端构建 | ✅ 通过（323 KB） |

- **已知问题**：见下方 [已知问题](#已知问题)

## 功能介绍

用一句中文完成商品管理，不需要点按钮。

```
你：查一下 iPhone15 的库存
你：卖了 2 个 iPhone15
你：iPhone15 打八折
你：这周的销售情况怎么样
```

系统会把你的话交给本地大模型（Qwen2.5-7B），由模型决定调用哪个工具、传什么参数，
再由后端执行真正的数据库操作。

**危险操作（删除、打折）会先弹确认框**，用户确认后才真正写库：

```
你：删除 小米手环8
系统：（弹窗）即将删除商品「小米手环8」，确认吗？
你：确定  →  已删除：小米手环8
```

## 支持的能力（范围）

### ✅ 稳定支持

| 能力 | 示例 |
|---|---|
| 查询商品 | "查一下 iPhone15 的库存"、"有哪些商品" |
| 新增商品 | "新增商品 蓝牙音箱 价格 199 库存 30" |
| 修改价格 / 库存 | "把 iPhone15 的价格改成 5799"、"机械键盘K8 库存改成 50" |
| 删除商品（带二次确认） | "删除 小米手环8" |
| 打折（带二次确认） | "iPhone15 打八折"、"给 iPadAir 打个五折" |
| 记录销售 / 进货 | "卖了 2 个 iPhone15"、"进货 10 个 机械键盘K8" |
| 查询销售 / 进货记录 | "最近的销售记录"、"昨天卖了什么" |
| 销售统计 | "这周的销售情况怎么样"、"卖了多少钱" |

### ⚠️ 有限支持

- **模糊表达**（"便宜的"、"卖得好的"）—— 依赖模型理解，不稳定
- **口语化的"补"**：说"补货 AirPodsPro 5 个"可以，说"补 5 个 AirPodsPro"会被拦下
  （模型不认得这个说法 → 未调工具 → 守卫按"未执行"处理，会请你换种说法）
- **多轮上下文**（"给它打八折"）—— 模型经常退化成"再查一次商品"而不是执行操作
- **商品名被改写** —— 模型可能把"机械键盘K8"传成"K8"，导致找不到商品

### ❌ 不支持

- 历史库存查询（"昨天库存多少"）
- 自主规划（"帮我做促销方案"）
- 多步推理（"对比一下"）
- 撤销/回滚已记录的销售与进货
- 用户登录与权限控制

## 架构要点

### AI 只提交申请，前端负责确认

写操作不直接落库，而是分两步：

```
用户说"删除 小米手环8"
   ↓
模型调用 delete_product  →  返回 {need_confirm: true, action: "delete", target: "小米手环8"}
   ↓
前端 confirm() 弹窗  →  用户点"确定"
   ↓
POST /api/chat/confirm  →  后端真正执行删除
```

### 幻觉守卫：没调工具就默认不信任

7B 模型有个危险行为：**不调用工具，却用文字声称"已经完成"**，
甚至编造库存数字（实测出现过"当前库存为 23"，而库里是 80）。

`backend/routes/chat_routes.py` 的做法是：

```python
if call.get("is_txt") and not call.get("tool"):
    if any(h in msg for h in SAFE_HINTS):      # 确认是闲聊/查询
        return success(...)                    # 原样返回
    return success(...)                        # 否则一律报"未执行任何操作"
```

关键是**白名单放在"闲聊"这一侧**（`SAFE_HINTS`）而不是"写操作"那一侧。
因为闲聊是封闭集合（你好/谢谢/天气…），写操作是开放集合
（卖掉/出货/清掉/处理掉/降下来/记一笔…），枚举不完。

> 💡 这也是为什么 `WRITE_HINTS` 现在没有被使用——它是早期"枚举写操作"的思路留下的，
> 已由 `SAFE_HINTS` + 默认不信任取代。可以删掉。

### 输入规范化：商品名统一去掉空格

`tools.py` 和 `routes/*.py` 里有 15 处 `replace(" ", "")`，让商品名**永远不含空格**。
这样"用户输入的名字"和"数据库里存的名字"总能精确匹配，规避模型多打/少打空格。

⚠️ 代价：新增商品时名字会被**静默改写**（`"Galaxy S24"` → 存成 `"GalaxyS24"`），
界面没有任何提示。见 [已知问题](#已知问题) 第 2 条。

## 已知问题

> 下面每一条都在 **MySQL 8.0.46 + Ollama qwen2.5:7b** 上实测复现过。

### 🟠 中等

**1. 商品名包含 `/` 时无法修改/删除**

新增 `"A/B测试"` 能成功，但按名字操作会失败：

```
PUT /api/products/A%2FB测试  →  HTTP 404 Not Found
```

原因：Flask 路由 `/api/products/<name>` 的 `<name>` 默认不匹配斜杠，
`%2F` 解码后同样是斜杠，路由匹配不上。

**修法**（二选一）：

```python
# 方案 A：改用 Flask 的 path 转换器（允许匹配斜杠）
@bp.route("/products/<path:name>", methods=["PUT"])
```

```python
# 方案 B（更推荐）：不用路径传名字，改用请求体
@bp.route("/products", methods=["PUT"])
def update_product():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    ...
```

**2. 新增商品时名字被静默改写**

```
POST /api/products {"name": "Galaxy S24"}  →  库里存成 "GalaxyS24"
```

用户输入什么名字，界面就该显示什么名字。建议至少在返回消息里说明：

```python
raw = body.get("name") or ""
name = raw.replace(" ", "").strip()
...
msg = "新增成功" + ("（原文中的空格已移除）" if raw != name else "")
```

**3. 修改失败却报"修改成功"**

`backend/services/tools.py`：

```python
rows = product_dao.update_product(name, fields)
return {"ok": True, "affected": rows, "message": f"修改成功：{name}"}
```

`rows` 拿到了但没检查。把价格改成**原值**时 MySQL 返回 `rowcount=0`，
仍然提示"修改成功"。建议：

```python
if rows == 0:
    return {"ok": True, "affected": 0, "message": f"{name} 的值没有变化"}
```

**4. 记录销售 + 扣减库存没有事务保护**

"写销售记录"和"扣库存"是两条独立 SQL、两个连接、各自 `commit()`。
正常路径实测一致，但任一步失败会出现"库存扣了、销售记录没有"，且无自动补偿。

**修法**：让两个 DAO 共用一个连接，包在同一个事务里：

```python
conn = get_conn()
try:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sales(...) VALUES(%s,%s,%s,%s)", (...))
        cur.execute("UPDATE product_lists SET stock=%s WHERE name=%s", (new_stock, name))
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
```

**5. 无分页、无 `LIMIT`**

实测 500 条销售记录 → `/api/sales` 一次返回 500 条、约 67 KB。
数据量再大响应体会等比膨胀。建议给查询接口加 `?limit=&offset=`。

**6. `get_by_name` 是精确匹配**

```python
cur.execute("SELECT id, name, price, stock FROM product_lists WHERE name=%s", (name,))
```

模型把"机械键盘K8"传成"K8"时直接报"商品不存在"。建议加模糊回退：
精确匹配失败时用 `WHERE name LIKE %s`（`%关键词%`）取最接近的一条。

### 🟡 轻微

| 问题 | 位置 | 说明 |
|---|---|---|
| `KeyError: 'is_txt'` 风险 | `services/product_service.py:12` | 用 `call["is_txt"]` 硬取值；工具名未知且无该键时会崩，建议改 `call.get("is_txt")` |
| `WRITE_HINTS` 已废弃未删 | `routes/chat_routes.py:8` | 已被 `SAFE_HINTS` 取代，留着会误导 |
| 进货页时间列永远空白 | `components/purchases-list/purchases-list.html:41` | 用了 `s.sold_at`，而进货记录字段是 `purchased_at` |
| 进货页文案是复制的 | `components/purchases-list/purchases-list.html:3` | 标题写"销售记录"；组件变量名叫 `sales`；`selector` 与销售页**完全相同** |
| 对话不持久化 | `database/init.sql:10-25` | `conversations` / `messages` 两张表建了但**零引用**（实测始终 0 行），刷新页面历史即丢失 |
| 无用的错误导入 | `services/tools.py:1` | `from email import message` |
| 实验残留文件 | `backend/test_pool.py` | 重复实现连接池、写死 `password='你的密码'`，放在后端根目录 |
| 只补了 1 个单测 | `components/product-list/product-list.spec.ts` | 其余组件、后端全部零测试 |

### 🧪 测试现状

```
Test Files  1 passed (1)
     Tests  1 passed (1)
```

目前只有 `product-list.spec.ts` 一个测试（验证商品列表能渲染出数据）。
`app.spec.ts` / `navbar.spec.ts` 等脚手架生成的模板断言已被删除。

**建议补的测试**（每个都很短，但能防住真实回归）：

```typescript
// 1. 正常路径：改库存应该成功（曾经因为一个 isinstance 打字错误全盘失效）
it('改库存应该返回成功', () => { /* expect(res.code).toBe(200) */ });

// 2. 参数校验：布尔值应该被拒绝
it('quantity 传 true 应该被拒绝', () => { /* expect(res.code).toBe(400) */ });

// 3. 幻觉守卫：没调工具时不应返回成功
it('AI 未调工具时不应返回 ok=true', () => { /* ... */ });
```

## 已知局限

本项目使用 **Qwen2.5-7B（Ollama 本地）** 做意图识别和工具调用。
由于 7B 模型的能力限制，**工具调用存在不稳定性**：

- AI 可能**没调工具**（直接回话），因此需要上面那套幻觉守卫
- AI 可能**改写参数**（"机械键盘K8" → "K8"，导致找不到商品）
- AI 可能**把 tool_call 语法泄漏成正文**（输出 `<tool_call>` 之类的原始文本）
- 同一个输入偶尔会有不同结果（实测 8 次里 1 次抖动；`temperature=0` + 固定 seed 大幅降低了概率但没消除）

**缓解措施**：

- 重试机制（3 次，不同 seed）
- `_is_tool_leak()` 检测并跳过泄漏的输出
- 危险操作二次确认
- `SAFE_HINTS` 白名单 + 默认不信任（幻觉守卫）
- 系统提示词里明确禁止"用文字声称已完成"

**但无法 100% 消除** —— 这是当前 LLM Agent 的普遍现状。

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| 后端框架 | Flask | 3.1.3 |
| 跨域 | flask-cors | 6.0.5 |
| 数据库驱动 | PyMySQL | 1.2.0 |
| 连接池 | DBUtils (PooledDB) | 3.1.2 |
| 环境变量 | python-dotenv | 1.2.3 |
| 大模型客户端 | ollama (Python) | 0.6.2 |
| 数据库 | MySQL | 8.0 |
| 大模型 | Qwen2.5-7B（Ollama 本地） | qwen2.5:7b |
| 前端框架 | Angular（standalone + signals） | 22 |
| 前端测试 | Vitest | 4.0.8 |
| 语言 | Python 3.12 / TypeScript 6.0 | — |

> 注意：`ollama` Python 库支持把 Python 函数直接当 `tools=` 传入
> （内部由 `convert_function_to_tool` 自动生成 JSON Schema），
> 所以 `TOOLS_FOR_AI = list(TOOL_FUNCTIONS.values())` 这样传函数是可用的。

## 快速开始

### 1. 准备环境

需要先装好并启动：**MySQL 8.0**、**Ollama**、**Python 3.12**、**Node.js + npm**。

```bash
# 拉取模型（约 4.4 GB）
ollama pull qwen2.5:7b
ollama serve
```

### 2. 建数据库

```bash
mysql -u root -p -e "CREATE DATABASE nlpilot CHARACTER SET utf8mb4;"
mysql -u root -p nlpilot < database/init.sql
```

### 3. 配置后端环境变量

```bash
cd backend
copy .env.example .env      # Linux/macOS 用 cp
```

然后编辑 `backend/.env`，**至少要改密码**：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=nlpilot

OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b

FLASK_PORT=5000
FLASK_DEBUG=true
```

### 4. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

看到 `Running on http://0.0.0.0:5000` 后，验证一下：

```bash
curl http://127.0.0.1:5000/api/health
# {"code":200,"data":"NLPilot running","message":"success"}
```

### 5. 启动前端

```bash
cd frontend
npm install
npm start
```

打开 **http://localhost:4200**。跑测试用 `npm test`。

> 前端请求地址写死在 `frontend/src/app/services/api.service.ts` 的
> `private base = 'http://localhost:5000/api'`，改了后端端口要同步改这里。

## 项目结构

```
NLPilot - Smart Admin/
├── backend/
│   ├── app.py                    # Flask 入口，注册蓝图
│   ├── config.py                 # 读 .env
│   ├── db.py                     # DBUtils 连接池（⚠️ 导入时就连 MySQL）
│   ├── response.py               # 统一响应格式 + HTTP 状态码
│   ├── dao/                      # 数据访问层（全部 SQL 参数化）
│   │   ├── product_dao.py
│   │   ├── sales_dao.py
│   │   └── purchases_dao.py
│   ├── services/
│   │   ├── nlu_service.py        # 调 Ollama，决定调哪个工具 + 重试 + 泄漏检测
│   │   ├── tools.py              # 10 个工具函数 + 注册表 TOOL_FUNCTIONS
│   │   └── product_service.py    # 按 AI 决策分发到工具
│   ├── routes/                   # 接口层
│   │   ├── chat_routes.py        # /api/chat、/api/chat/confirm（含幻觉守卫）
│   │   ├── product_routes.py     # /api/products
│   │   ├── sales_routes.py       # /api/sales
│   │   └── purchases_routes.py   # /api/purchases
│   └── prompts/system_prompt.py  # 系统提示词
├── frontend/src/app/
│   ├── app.routes.ts             # 4 个路由：chat / products / sales / purchases
│   ├── services/api.service.ts
│   ├── models/product.model.ts
│   └── components/               # chat / product-list / sales-list / purchases-list / navbar
└── database/init.sql             # 建表脚本
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/products?name=` | 查询商品（`name` 模糊匹配，可省略） |
| POST | `/api/products` | 新增商品 `{name, price, stock}` |
| PUT | `/api/products/<name>` | 修改 `{price?, stock?}` |
| DELETE | `/api/products/<name>` | 删除商品 |
| GET | `/api/sales?name=&days=` | 查询销售记录 |
| POST | `/api/sales` | 记录销售 `{name, quantity, unit_price?}` |
| GET | `/api/sales/summary?name=&days=` | 销量汇总 |
| GET | `/api/purchases?name=&days=` | 查询进货记录 |
| POST | `/api/chat` | 自然语言入口 `{message, history}` |
| POST | `/api/chat/confirm` | 二次确认 `{action, target, data}` |

**响应格式**（HTTP 状态码与 `code` 字段一致）：

```json
// 成功：HTTP 200
{ "code": 200, "message": "success", "data": {} }

// 失败：HTTP 400 / 404 / 409 / 500
{ "code": 404, "message": "商品 iPhone15 不存在", "data": null }
```

前端 `chat.ts` 的 `_handleError` 按 HTTP 状态码分类提示，
所以**后端必须返回真实的 HTTP 状态码**，不能一律 200。

## 常见问题

**Q：后端启动就崩，报 `Can't connect to MySQL server` / `OperationalError (2003)`**

`backend/db.py` 在 **模块导入时** 就用 `mincached=2` 建立连接池，
所以 MySQL 没启动的话后端根本起不来，而且报错栈全是连接池内部调用，
看不出真实原因。请先确认 MySQL 已启动、`.env` 里的密码正确。

**Q：`pip install` 或 `python app.py` 报 `ModuleNotFoundError: No module named 'dbutils'`**

虚拟环境没激活，或依赖没装。用虚拟环境里的解释器直接跑：
`.venv\Scripts\python.exe app.py`。

**Q：页面能打开、商品列表有数据，但对话报错或没反应**

Ollama 没启动，或没拉模型。检查：

```bash
curl http://127.0.0.1:11434/api/tags
ollama pull qwen2.5:7b
```

**Q：AI 回"我没能理解你的操作意图，请换一种说法重试（未执行任何操作）"**

这是**幻觉守卫生效**，不是 bug。说明模型没有调用工具（可能它想用文字
向你请求确认，或者不认得你的说法）。换一种更明确的说法即可，例如：

| 被拦下的说法 | 换成 |
|---|---|
| "补 5 个 AirPodsPro" | "补货 AirPodsPro 5 个" |
| "帮我处理掉 AirPodsPro" | "删除 AirPodsPro" |
| "帮我把 iPhone15 价格降下来" | "把 iPhone15 价格改成 4799" |

**关键是这次操作绝对没有执行**——不会出现"以为卖掉了其实没卖"的情况。

**Q：新增商品时名字里的空格消失了**

这是当前的设计（统一 `replace(" ", "")`），为了让"用户输名字"和
"数据库里存的名字"能精确匹配。**但没有任何提示**，属于已知问题。

**Q：重复执行 `database/init.sql` 报 `Table 'product_lists' already exists`**

该脚本里 `product_lists` / `conversations` / `messages` 三张表没有
`IF NOT EXISTS`，重复执行会报错。重建请先 `DROP DATABASE nlpilot`。

## 版本历史

- v0.1：基础 CRUD + prompt+JSON 意图识别
- v0.2：Function Calling + 销售/进货模块
- v0.3：重试机制 + tool_call 泄漏检测 + 幻觉拦截（关键词白名单）
- v0.4：当前版本
  - 修复 `POST /api/sales` 缺 `name` 时的 500 崩溃
  - 修复 `PUT /api/products` 的 `stock` 校验恒真错误（导致改库存完全失效）
  - 补齐全部布尔值校验（`isinstance(x, bool)`）
  - `error()` 返回真实 HTTP 状态码（激活前端错误处理）
  - 修复前端 `getBought` 的参数名（`day` → `days`）
  - 幻觉守卫改为 `SAFE_HINTS` 白名单 + 默认不信任（幻觉 0/17、误伤 0/8）
  - 系统提示词明确禁止"用文字声称已完成"
  - 补上第一个真正的单元测试

## 后续计划

- 修「商品名含 `/` 无法改删」（改用请求体传名字）
- 把"写记录 + 改库存"包进同一个事务
- `get_by_name` 加模糊回退，容忍模型改写商品名
- 分清"加 50"与"改成 50"的数量语义
- 查全表加 `LIMIT` / 分页
- 补齐单元测试（至少覆盖：正常改库存、布尔被拒、幻觉守卫）
- 对话持久化（用掉已经建好的 `conversations` / `messages` 表）
- 清理：删掉 `WRITE_HINTS`、`from email import message`、`backend/test_pool.py`
- 更稳的工具调用（换更大模型 / 微调）
- 多步推理（ReAct）
- 语义搜索（embedding）
