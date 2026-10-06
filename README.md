# NLPilot - 智能商品管理系统

自然语言驱动的商品管理系统。用对话完成商品的增删改查。

## 技术栈

- 前端：Angular
- 后端：Flask + PyMySQL + DBUtils
- 数据库：MySQL 8
- AI：Ollama + Qwen2.5

## 功能

- 自然语言查询、新增、修改、删除商品
- 删除操作二次确认
- 统一响应格式 `{code, message, data}`

## 快速开始

### 1. 数据库
```bash
mysql -u root -p < database/init.sql
```
### 2. 后端
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # 修改数据库密码
python app.py
```
### 3. 前端
```bash
cd frontend
npm install
ng serve
```
### 4. AI 模型
```bash
ollama pull qwen2.5:7b
```
### 使用示例
```text
查一下 iPhone 的库存
→ 共 1 条：iPhone 15  ¥5999.00  库存 120

添加商品 AirPods，价格 999，库存 50
→ 新增成功：AirPods
```
项目结构
text
backend/    Flask 后端
frontend/   Angular 前端
database/   SQL 脚本