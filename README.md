# NLPilot - 智能商品管理系统

> 自然语言驱动的商品管理系统。
> 用对话完成商品的增删改查、销售/进货记录、数据统计。
>
> ⚠️ **实验性项目** —— 基于 7B 模型的 AI 工具调用，稳定性有限。

---

## ⚠️ 当前状态

| 项 | 值 |
|---|---|
| **版本** | **v0.2（L2）** |
| **成熟度** | **实验性 / Demo** |
| **AI 模型** | **Qwen2.5-7B（Ollama 本地）** |
| **已知局限** | **见下文** |

---

## ✅ 支持的能力

### 稳定支持

| 操作 | 例子 |
|---|---|
| **查询商品** | "查一下 iPhone" |
| **新增商品** | "新增商品 AirPods，价格 999，库存 50" |
| **修改商品** | "把 iPhone 15 的价格改成 5999" |
| **删除商品** | "删掉 iPad Air"（带确认） |
| **打折** | "给 iPhone 15 打八折"（带确认） |
| **记录销售** | "卖了 2 台 iPhone 15" |
| **记录进货** | "进了 10 个 AirPods" |
| **查询销售记录** | "昨天卖了什么" |
| **查询进货记录** | "最近进了什么货" |
| **销售统计** | "这周销售情况" |

### 有限支持

| 能力 | 说明 |
|---|---|
| **模糊表达** | "便宜的耳机"、"卖得好的" —— 依赖模型理解 |
| **多轮上下文** | "给它打八折" —— 能理解"它"指代上文商品，但有限 |
| **复杂语义** | 多重条件、嵌套逻辑 —— 不稳定 |

### 不支持

| 需求 | 原因 |
|---|---|
| **历史库存查询** | "昨天库存多少" —— 未记录库存历史 |
| **自主规划** | "帮我做个促销方案" —— 需要多步推理 |
| **多步对比** | "昨天比前天卖得多吗" —— 单步工具调用做不了 |
| **图表展示** | 无图表组件 |
| **批量操作** | "把所有耳机打八折" —— 未实现 |

---

## ⚠️ 已知局限

本项目使用 **Qwen2.5-7B（Ollama 本地部署）** 做意图识别和工具调用。
由于 7B 模型的能力限制，**工具调用存在不稳定性**：

### 可能的问题

| 问题 | 例子 |
|---|---|
| **AI 没调工具** | 用户问"查库存"，AI 直接回话 |
| **AI 调错工具** | "查库存" → 调用了 `record_sale` |
| **AI 参数错误** | 数字被识别为字符串 |
| **AI 理解偏差** | 复杂指令被简化 |

### 缓解措施

| 措施 | 说明 |
|---|---|
| **重试机制** | 最多 3 次，每次不同 seed |
| **prompt 调优** | 明确"何时用/不用"工具 |
| **危险操作确认** | 删除、打折需用户二次确认 |
| **日志** | 记录每次 AI 决策，便于排查 |

**但无法 100% 消除** —— 这是当前 LLM Agent 的普遍现状。
即使 GPT-4 / Claude 的 Agent 也存在类似问题。

---

## 🛠 技术栈

| 层次 | 技术 |
|---|---|
| **前端** | Angular 19+（standalone + signals + 控制流） |
| **后端** | Python Flask |
| **数据库** | MySQL 8 |
| **数据库驱动** | PyMySQL + DBUtils（连接池） |
| **AI 模型** | Ollama + Qwen2.5-7B |
| **AI 调用方式** | Function Calling（tools 参数） |
| **通信** | HTTP + JSON |

---

## 📁 项目结构

```
NLPilot-Smart-Admin/
├── backend/                       # Flask 后端
│   ├── app.py                     # 入口
│   ├── config.py                  # 配置
│   ├── db.py                      # 连接池
│   ├── response.py                # 统一响应
│   ├── requirements.txt
│   ├── .env.example               # 环境变量模板
│   ├── dao/                       # 数据访问层
│   │   ├── product_dao.py
│   │   ├── sales_dao.py
│   │   └── purchases_dao.py
│   ├── routes/                    # 路由层
│   │   ├── product_routes.py
│   │   ├── chat_routes.py
│   │   ├── sales_routes.py
│   │   └── purchases_routes.py
│   ├── services/                  # 服务层
│   │   ├── tools.py               # AI 工具定义
│   │   ├── nlu_service.py         # 调 Ollama
│   │   └── product_service.py     # 工具分发
│   └── prompts/                   # 提示词
│       └── system_prompt.py
│
├── frontend/                      # Angular 前端
│   └── src/app/
│       ├── components/
│       │   ├── chat/              # 对话界面
│       │   ├── navbar/            # 导航栏
│       │   ├── product-list/      # 商品列表
│       │   ├── sales-list/        # 销售记录
│       │   └── purchases-list/    # 进货记录
│       ├── services/
│       │   └── api.service.ts
│       └── app.routes.ts
│
└── database/
    └── init.sql                   # 建表 + 初始化
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0+
- Ollama（[官网](https://ollama.com)）

### 1. 数据库

```bash
mysql -u root -p < database/init.sql
```

创建库 `nlpilot`，包含表：
- `product_lists`（商品）
- `sales`（销售记录）
- `purchases`（进货记录）

### 2. 后端

```bash
cd backend

# 虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux

# 依赖
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env，填入 MySQL 密码

# 启动
python app.py
```

后端运行在 `http://localhost:5000`

### 3. 前端

```bash
cd frontend
npm install
ng serve
```

前端运行在 `http://localhost:4200`

### 4. AI 模型

```bash
# 安装 Ollama（如果没装）

# 拉取模型
ollama pull qwen2.5:7b

# 确认
ollama list
```

---

## ⚙️ 环境变量

`backend/.env` 示例：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=nlpilot

OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b

FLASK_PORT=5000
FLASK_DEBUG=true
```

---

## 🔌 API 接口

### 对话接口

**`POST /api/chat`**

```json
// 请求
{
  "message": "查一下 iPhone",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}

// 响应
{
  "code": 200,
  "message": "共 1 条",
  "data": {
    "call": {"tool": "query_products", "args": {"name": "iPhone"}},
    "result": {"ok": true, "count": 1, "data": [...]}
  }
}
```

### 确认接口

**`POST /api/chat/confirm`** —— 危险操作二次确认

```json
{
  "action": "delete",
  "target": "iPhone 15"
}
```

### 只读接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/products` | 查询商品（支持 `?name=xxx`） |
| `GET` | `/api/sales` | 查询销售记录（支持 `?name=xxx&days=30`） |
| `GET` | `/api/purchases` | 查询进货记录 |
| `GET` | `/api/dashboard` | 主页统计（昨日售出/进货） |

---

## 🧠 核心流程

```
用户输入自然语言
    ↓
前端 POST /api/chat（带 history）
    ↓
后端 nlu_service 调 Ollama（带 tools）
    ↓
AI 输出 tool_calls
    ↓
product_service 分发到对应工具
    ↓
工具调用 dao 操作数据库
    ↓
返回结果给前端
```

**关键设计**：
- **AI 只输出"调哪个工具"，代码负责执行**
- **危险操作（删除、打折）需用户二次确认**
- **对话记忆通过前端传 `history` 实现**

---

## 📋 版本历史

### v0.2（L2）—— 当前

- ✅ **Function Calling**：AI 直接调工具（不再输出"意图"）
- ✅ **对话记忆**：支持上下文引用
- ✅ **10 个 AI 工具**
- ✅ **销售/进货模块**（表 + DAO + 页面）
- ✅ **主页统计**（昨日售出/进货）
- ✅ **重试机制**（最多 3 次）
- ✅ **危险操作确认**（删除、打折）

### v0.1（L1）

- ✅ 基础 CRUD
- ✅ prompt + JSON 意图识别
- ✅ 删除二次确认

---

## 🔮 后续计划

### 短期

- [ ] **prompt 调优** —— 提升工具调用稳定性
- [ ] **扩展"确认"** —— 所有写操作都确认
- [ ] **优雅拒绝** —— 不在范围时明确拒绝，不乱调工具

### 中期

- [ ] **换更大模型** —— Qwen2.5-14B / 32B
- [ ] **多步推理（ReAct）** —— 支持"对比"、"分析"
- [ ] **图表展示** —— 销售趋势折线图

### 长期

- [ ] **语义搜索** —— embedding，支持"便宜的"、"卖得好的"
- [ ] **RAG** —— 检索增强生成
- [ ] **Qt 桌面客户端**
- [ ] **微调专用模型**

MIT

---
