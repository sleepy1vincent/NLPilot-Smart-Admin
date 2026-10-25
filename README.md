# NLPilot · 智能商品管理系统

> 用一句中文完成商品管理。本地 7B 模型负责理解与决策，工具负责执行与陈述事实，向量检索只在两处兜底。

**v3.1** ｜ Python 3.12 · Flask 3.1 · MySQL 8.0 · Angular 22 · Ollama（qwen2.5:7b + bge-m3）

📊 **[架构全景图（交互式）](docs/architecture-v3.html)** ｜ 静态预览：[PNG](docs/architecture-v3.png)

---

## 当前状态

- **版本**：v3.1（在 v3.0 的 RAG 基础上，重做了推荐选取与幻觉防护）
- **成熟度**：可演示 / Demo

### 验收实测（MySQL 8.0.46 + Ollama qwen2.5:7b + bge-m3）

| 验收项 | 结果 |
|---|---|
| AI 工具选择准确率 | **14/14 = 100%** |
| 幻觉「冒领执行」用例 | **11/11 可辨识**（结构方案；原正则 10/11） |
| 正常问答误伤 | **0/8** |
| 参数校验（布尔 / 边界） | **9/9 正确** |
| HTTP 状态码 | **6/6 正确** |
| 销售事务原子性（故障注入） | ✅ 两表均无残留 |
| 并发超卖（10 线程抢 5 库存） | ✅ 恰好成功 5 次，库存归零 |
| RAG 场景词召回 | ✅ **6/7** |
| RAG 无关查询拦截 | ✅ **4/4** |
| 推荐相关性（送女朋友礼物） | ✅ 只出 2 个真实相关，不再凑第 3 个 |
| 商品名容错（iphone → iPhone15） | ✅ 唯一命中自动纠正，多候选反问 |
| 新增商品自动打标 | ✅ AI 路径 + HTTP 路径均生效 |
| 前端构建 / 单元测试 | ✅ 构建通过 · 1 passed |

---

## 这个项目是什么

一个**用自然语言操作商品库**的管理系统。不点按钮，直接说话：

```
你：查一下 iPhone15 的库存
你：卖了 2 个 iPhone15
你：能听歌的有什么          ← 名字里没有"听歌"，靠语义检索命中
你：适合办公的推荐一下
你：这周的销售情况怎么样
```

系统把这句话交给本地模型（qwen2.5:7b），由模型决定调哪个工具、传什么参数，
再由后端执行真正的数据库操作。

**危险操作会先弹确认框**：

```
你：删除 小米手环8
系统：（弹窗）即将删除商品「小米手环8」，确认吗？
你：确定  →  已删除：小米手环8
```

---

## 核心能力

### ✅ 稳定支持

| 能力 | 示例 |
|---|---|
| 查询商品（按名） | "查一下 iPhone15 的库存"、"有哪些商品" |
| **结构化筛选** | **"有哪些耳机"、"500 以内有什么"、"有货的"、"最便宜的配件"** |
| **推荐（按用途 / 预算）** | **"推荐个送女朋友的礼物"、"500 以内送什么好"、"有什么适合学生党的"** |
| **语义查询（按意思）** | **"能听歌的"、"适合办公的"、"出差带着充电的"** |
| 新增商品（自动打标） | "新增商品 蓝牙音箱 价格 199 库存 30" |
| 修改价格 / 库存 | "把 iPhone15 的价格改成 5799" |
| 删除商品（二次确认） | "删除 小米手环8" |
| 打折（二次确认） | "iPhone15 打八折" |
| 记录销售 / 进货 | "卖了 2 个 iPhone15"、"进货 10 个 机械键盘K8" |
| 查询销售 / 进货记录 | "最近的销售记录"、"昨天卖了什么" |
| 销售统计 | "这周的销售情况怎么样" |

### ⚠️ 有限支持

- **推荐结果不含图片/评价**：`recommend_products` 只用标签和描述做排序依据
- **多轮上下文**（"给它打八折"）：模型经常退化成"再查一次商品"
- **口语化的"补"**：说"补货 XX 5 个"可以，说"补 5 个 XX"会被模型理解成查询
- **完全改写的商品名**：`iphone`→`iPhone15` 能自动纠正，但"苹果手机"这类
  完全不沾字面的说法会走"请说完整商品名"的反问（不做语义猜测）

### ❌ 不支持

- 撤销 / 回滚已记录的销售与进货
- 用户登录与权限控制
- 政策类问答（退货、发票、物流）—— 知识库里没有数据

---

## 架构总览

![架构图](docs/architecture-v3.png)

```
用户浏览器
   ↓ HTTPS
Angular 前端（对话 / 商品 / 销售 / 进货）
   ↓ HTTP JSON /api/*     ← 响应拆两个通道：result（事实）/ reply（对话）
┌────────────── Flask 后端（单进程）──────────────┐
│  Flask 路由层          11 个接口 · :5001         │
│        ↓ 识别与分发                              │
│  服务层   意图识别 · 11 个工具 · 名称解析 · RAG    │
│        ↓ 事务读写                                │
│  数据访问层          DAO · 连接池 · Transaction    │
└──────────────────────────────────────────────────┘
   ↓ SQL                        ↘ 向量只在两处：语义兜底 / 推荐召回
MySQL 8.0                          ChromaDB 向量库
（唯一事实来源）                    （只负责找 id）
```

**旁挂外部服务**：Ollama —— `qwen2.5:7b` 负责工具调用与打标，`bge-m3` 负责向量嵌入。

### 一条主线：模型决策，工具执行，两个通道分别呈现

```
用户："卖出 iphone 50 台"
   │
   ├─ 模型：听懂 → 选 record_sale，参数 {product_name:"iphone", quantity:50}
   │         （只是"决定做什么"，没有说结果——它也不知道结果）
   ├─ 服务层：名称解析 "iphone" → "iPhone15"（精确 → LIKE，不做语义猜测）
   ├─ 工具：事务内扣库存 + 写销售记录，返回 {ok, sale_id, new_stock:95}
   │
   └─ 响应：
        result = {kind:"tool", ok:true, message:"已记录销售：iPhone15 × 50，剩余库存 95"}
        reply  = ""        ← 有事实就不让模型复述，杜绝"说错数字"
```

前端把 `result` 画成绿色结果卡片、把 `reply` 画成对话气泡（无工具调用时附带
「对话回复 · 本次未执行数据库操作」标记）。**用户永远能分清"它做了"和"它说了"。**

### 三条互不重叠的调用链

| 链路 | 入口 | 路径 |
|---|---|---|
| **AI 对话** | `POST /api/chat` | 路由 → 意图识别 → 名称解析 → 工具 → DAO |
| **REST 直连** | `GET/POST /api/products`、`/api/sales` | 路由 → DAO（**跳过 AI 层**） |
| **二次确认** | `POST /api/chat/confirm` | 路由 → DAO |

> 容易忽略的一点：`/api/products`、`/api/sales` 这类接口**不经过 AI**，直接调 DAO。

### 分工边界：什么交给模型，什么交给代码

| 任务 | 谁负责 | 为什么 |
|---|---|---|
| 听懂"送女朋友的礼物" | 模型 | 开放语言，规则枚举不完 |
| 选哪个工具、填什么参数 | 模型 | 需要语义判断 |
| **商品名对齐**（iphone → iPhone15） | **代码** | 字符串问题，确定性算法更可靠 |
| **精确查询 / 结构化筛选** | **代码（SQL）** | 0.13~0.73ms，比向量快几百倍 |
| **语义兜底 / 推荐召回** | 向量 | 只有"字面完全不沾"时才需要 |
| **陈述操作结果** | **工具返回值** | 模型没有记账权 |

---

## 关键技术设计

### 1. 幻觉防护：不给模型"记账权"，而不是判断它有没有撒谎

7B 模型有个危险行为：**不调用工具，却用文字声称"已经完成"**，甚至编造库存数字。
实测出现过："记录了一笔 iPhone15 的销售。您卖出了 2 台，当前剩余 143 台。" —— 而数据库毫无变化。

**这类"冒领执行"是危害最大的一类幻觉**：用户以为删了、其实没删，数据继续被污染，
而且用户没有任何线索能发现。

#### 走过的弯路（这部分是设计取舍的依据）

最初的做法是**用规则判断模型有没有撒谎**，最终累积到约 190 条：

```
CLAIM_PATTERNS（10 条）· SAFE_HINTS（22 条）· SMALLTALK_RE（30 分支）
DENIAL_RE（20 分支）· CLARIFY_RE（16 分支）· RESULT_RE（12 分支）
```

三个实测结论让我们放弃了这条路：

| 方案 | 同批 11 条用例 | 问题 |
|---|---|---|
| 正则守卫 | 拦对 5/6，放对 5/5 | 换个说法就漏（"已删除"→"已经帮你删掉了"→"帮你删好了"…） |
| 7B 当审核员·**无证据** | 拦对 **0/6** | 11 条全判 pass，等于没加，只多了 1.7 秒 |
| 7B 当审核员·**带证据** | 拦对 **1/6** | 会把"用户请求"当成"已发生的事实"；换提示词措辞就从 0/6 变 3/6 |

> 审核员的失败案例很典型：用户说"卖了 2 个"，执行记录为空，回复"已记录销售"，
> 它判 pass 的理由是"**与用户请求一致**"——把意图当成了事实。

#### 现在的做法：通道分离，取消"记账权"

```
副作用   只能通过工具发生（模型不调工具，数据库就不会变）
操作结果 只能由工具返回值陈述（含 rowcount）
没有工具调用 ⇒ 本次没有任何数据库操作（tool_calls 为空的直接推论，无需任何文本判断）
```

`guard_service.py` 从 197 行缩到 49 行（其中 34 行是注释），核心只有一个函数：

```python
def inspect(call: dict) -> dict:
    tool = call.get("tool")
    if tool:
        return {"executed": True,  "tool": tool}
    return {"executed": False, "tool": None}
```

**零文本解析。** 响应拆成两个通道：

```json
{
  "executed": true,
  "result":   { "kind": "tool", "ok": true, "count": 2, "data": [...] },   // 事实
  "reply":    ""                                                          // 有事实时丢弃模型的话
}
```

```json
{
  "executed": false,
  "result":   { "kind": "none", "ok": false },        // 事实：什么也没发生
  "reply":    "已删除 iPhone15，库存已清空。"          // 模型的话，前端单独标注
}
```

#### 前端把两个通道画成两种东西

```
┌─ 操作结果 · 来自数据库 ──────────────┐
│ 找到 1 条                            │    ← 绿色卡片，内容只来自工具返回值
│ · iPhone15  ¥5999.00  库存 145        │
└──────────────────────────────────────┘

        已删除 iPhone15，库存已清空。         ← 普通气泡（模型的话）
        ┃ 对话回复 · 本次未执行数据库操作      ← 灰色标记（结构事实）
```

**关键机制是对照**：用户看到"已删除"的同一屏上，写着"本次未执行数据库操作"。
谎言活不下去，不是因为模型变诚实了，而是因为**它旁边永远摆着账本**。

#### 还有一个意外收益

原来正则漏掉的那条——**"只查了却声称改了"**（`tool=query_products` 但回复说"已把价格改为 5799"）——
在通道分离下自动解决了：**只要调用了工具，模型的文字就被丢弃**，那句假话根本到不了用户面前。

```
修复前：正则 10/11（漏 1 条）
修复后：结构方案 11/11
```

#### 但文字判断不是完全没价值

`rowcount` 只能证明"改动了一行"，证明不了"回复里描述的数字对不对"。
这类"结果失真"（实际卖 2 个，回复说卖了 5 个）只能靠语义核对，
但那是**窄任务**（核对数字是否出现在证据里），不是**开放式真伪判断**——后者 7B 做不到（55%）。

**当前取舍**：宁可放弃这一层，也不引入一个 55% 准确的、不确定的守门员。

`/api/chat/confirm` 里仍然保留 `rowcount == 0` 判断（曾出现"价格没变却报已更改"）：

```python
rows = product_dao.update_product(target, {"price": data})
if rows == 0:
    return success(data={"affected": 0}, message=f"{target} 的价格已经是 {data}，未做修改")
```

> 原则：**不要相信模型的自述，也不要只相信工具返回的 `ok`，只相信受影响行数。**


### 2. 事务边界：DAO 不管事务，业务层统一管

"写销售记录"和"扣库存"必须同生共死。早期写法是两个 DAO 各开连接、各 `commit()`，
任一步失败就会留下半个状态。

现在：

```python
with Transaction() as conn:                     # 事务从这里开始
    with conn.cursor() as cur:
        cur.execute("SELECT ... FOR UPDATE")    # 读库存 + 行锁
        sales_dao.record_sale(..., cursor=cur)  # 不 commit
        cur.execute("UPDATE product_lists ...")  # 同一游标 = 同一事务
# 正常退出 COMMIT；抛异常 ROLLBACK；无论如何归还连接
```

DAO 因此支持"借用"：传 `cursor=` / `conn=` 时不 commit、不 close，控制权交给调用方。

**实测（故障注入，让扣库存失败）**：

```
sales 0 → 0   库存 145 → 145   ✅ 已回滚，无孤儿记录
```

### 3. 行级锁：`SELECT ... FOR UPDATE` 防并发超卖

"读库存 → 判断 → 写库存"之间隔着两次网络往返，两个请求会读到同一个值，双双判断"够卖"。
事务内加行锁后，后到的请求会阻塞等待，拿到锁时读到的是已更新的库存。

**实测（10 线程同时卖同一商品，库存只够 5 个）**：

```
成功 5 次，失败 5 次   sales=5   库存=0   ✅ 未超卖
```

> 前提：`FOR UPDATE` 必须在事务里才有效（本项目 `autocommit=False`）。

### 4. 数据质量自检：缺标签是静默的

打标是 best-effort（失败只打印一句）。这意味着 Ollama 抖一下、或手工插一条数据，
就会留下"没有描述"的商品——**它不报错，只是悄悄失去语义检索能力**。

`backend/app.py` 的启动自检：

```
[自检] ✅ 10/10 个商品都有描述，语义检索完整
```

缺失时打印警告 + 补全命令，但**绝不自动补标**（否则启动会被 LLM 拖垮，
且 Ollama 一挂后端就起不来）。

`GET /api/health` 同时暴露覆盖率：

```json
{"data_quality": {"products": 10, "with_description": 10},
 "rag": {"ok": true, "vectors": 10}}
```

---

## RAG 链路详解

### 定位：它是兜底，不是主路径

```
① 结构化查询（SQL LIKE）   —— 99% 的情况走这里，0.13~0.73 ms
   ↓ 查不到
② 语义召回（RAG）          —— 只有 SQL 干不了才触发，约 230 ms
   ↓ 距离超过阈值
③ 明确说"没找到"           —— 绝不编造
```

**为什么 RAG 只做兜底**：实测 200 个商品，SQL 查名字 **0.13~0.73ms**，
向量检索 **211~353ms** —— 慢 **343~2628 倍**。用向量匹配商品名是纯粹的浪费。

### 写入路径：索引怎么建起来

```
新增商品（AI 或 HTTP 路径）
   ↓
① product_dao.insert_product()         纯 SQL、先提交（商品一定建成）
   ↓
② enrich_services.tag(name)            qwen2.5:7b 生成三件套
      → {category:"耳机", tags:["通勤","降噪"],
         description:"无线蓝牙耳机，通勤听歌都合适"}
   ↓
③ product_dao.save_enrichment()        写回 MySQL 三个字段
   ↓
④ rag_services.upsert_product(row)     建索引
      → _doc() 拼接："AirPodsPro 耳机 通勤 降噪 无线蓝牙耳机，通勤听歌都合适"
      → bge-m3 变 1024 维向量
      → Chroma upsert
```

**三条纪律**：

| 纪律 | 原因 |
|---|---|
| **先打标、再索引** | 反了就索引里只有名字，描述检索对它永远失效 |
| **打标不能阻塞/回滚新增** | Ollama 挂了也必须能加商品（加商品与 AI 无关） |
| **打标在事务提交之后** | 否则 LLM 的几秒钟会把事务和连接一起占住 |

批量补标（历史数据 / 导入数据）：

```bash
cd backend && python scripts/auto_tag.py
```

逻辑相同，只是源头是 `WHERE description IS NULL OR description = ''`，
并且会**同步向量库**（否则 MySQL 补好了、索引还是旧的）。

### 读取路径：一次查询的完整旅程

以「**能听歌的**」为例：

```
① nlu_service.recognize()
   qwen2.5:7b 从工具表里选出 query_products(name="能听歌的")
      ↓
② tools.query_products("能听歌的")
      ├─ SQL: WHERE name LIKE '%能听歌的%'  → 0 条   ✗
      ↓
③ rag_services.search_products("能听歌的", top_k=3)
      ├─ bge-m3 把 query 变向量        ~156 ms
      ├─ Chroma cosine 检索            ~76 ms
      └─ 返回 [("2", 0.446), ("11", 0.61), ("3", 0.62)]
      ↓
④ 阈值过滤 distance <= 0.53 → [("2", 0.446)]
      ↓
⑤ product_dao.get_by_ids([2])
      回查 MySQL 拿真实价格、库存、描述
      → {id:2, name:"AirPodsPro", price:1899, stock:80, ...}
      ↓
⑥ 返回 {"ok":true, "count":1, "data":[...], "is_rag":true}
      ↓
⑦ 前端渲染："共 1 条：· AirPodsPro ¥1899.00 库存 80"
```

### 索引里存了什么

```
Chroma collection: product_v2     度量：cosine
每条记录：
  id        : "2"
  document  : "AirPodsPro 耳机 无线 降噪 通勤 无线蓝牙耳机，通勤听歌都合适"
  embedding : 1024 维向量
  metadata  : {"category": "耳机"}
```

文档拼接规则：

```python
def _doc(p):
    parts = [p["name"], p["category"], p["tags"].replace(",", " "), p["description"]]
    return " ".join(x for x in parts if x and x.strip())
```

**为什么四段都要拼**：名字保证精确命中距离≈0；品类和标签补上用户可能说的词；
描述承载"能听歌的""适合办公的"这类真正的**意图**。

### 为什么价格库存不放进向量库

实测过：把 `price/stock` 作为 metadata 存进 Chroma，卖 30 个之后：

| 来源 | 价格 | 库存 |
|---|---|---|
| MySQL（真实） | 5999.00 | **115** |
| RAG（快照） | 5999.00 | **145** ← 过期 |

**向量库只负责"找到 id"，MySQL 才是唯一事实来源。**

### 泛化的三层来源

```
第 1 层  SQL LIKE         覆盖"用户说的词在名字里"      快、准、可解释
   ↓ 查不到
第 2 层  向量语义召回      覆盖"描述里出现过相近意思"     中速、能容错
   ↓ 距离 > 阈值
第 3 层  明确说"没找到"    覆盖"真的没有"               安全，绝不编造
```

### 推荐为什么要叠一层字面规则

`recommend_products` 最初是"纯向量 + 宽松阈值（0.75）+ 取前 3 个"，
实测暴露了问题——问"送我女朋友什么礼物"，第 3 个推荐是**机械键盘**。

查了真实距离分布才知道原因：

```
查询"给我一个送给女朋友礼物的建议"
  1  0.453  iPhone15        ★ tags 含"送礼"
  2  0.509  充电宝20000mAh   ★ tags 含"送礼"
  3  0.551  小米12           （无送礼信息）
  5  0.567  机械键盘K8        （无送礼信息）
 10  0.583  显示器27寸
```

**10 个商品的向量距离全挤在 0.45~0.58 这 0.13 的区间里**，
0.75 的阈值等于没设，系统只能"凑满 3 个"——凑出来的就是无关商品。

#### 试过但不采用的两条路

**① 同义词表 + 字面打分**（做了一版，后来删掉）

```python
SYNONYMS = {"礼物": ["送礼", "礼品"], "女朋友": ["女生", "女性"], ...}   # 18 个键 / 60 个词
```

能用，但它是**穷举**：用户换个说法就得加一行，永远补不完。
真实的推荐系统不该靠维护词表。

**② HyDE：让模型把需求扩写成"理想商品"，再检索**（试了，效果更差）

这是工业界的常用技术，思路是对的，但在**小语料**上会翻车：

| 查询 | 原始 query 检索 | HyDE 扩写后检索 |
|---|---|---|
| 送女朋友的礼物 | **iPhone15 0.460 / 充电宝 0.505** ✅ | 机械键盘 0.511 / 小米手环 0.517 ❌ |
| 降噪耳机 | **12 0.312 / AirPodsPro 0.337** ✅ | MacBook 0.343 排第一 ❌ |

原因：模型把需求扩写成"施华洛世奇手链"，而**库里没有手链**——
生成的向量落在语料分布之外，最近邻全是噪声。
HyDE 的前提是"生成文本与文档同分布"，11 个商品的库不满足这个前提。

#### 最终方案：纯向量 + **相对阈值**

```python
best   = min(dist.values())            # 最优距离
cutoff = best + 0.08                   # 只保留"离最优不远"的
if best > 0.55:                        # 连最优都太远 → 库里真没有
    return "库里没有适合「X」的商品"
```

两个阈值都是**实测标定**的，不是拍脑袋：

```
库里"有对应商品"的最优距离：0.310 ~ 0.518
库里"没有对应商品"的最优距离：0.580 ~ 0.623
                          ↑ 间隙 0.518~0.580
→ 绝对阈值取 0.55（两侧留余量）；相对阈值取 0.08（同批次内部比较用）
```

**核心原则：宁可少推荐，也不要凑数。**

```
"送女朋友的礼物"   → 2 个（iPhone15 / 充电宝）
"学生党"          → 1 个（iPadAir）
"降噪耳机"        → 2 个（12 / AirPodsPro）
"上班办公用的"     → 3 个
"有没有适合钓鱼的"  → 0 个，如实说"库里没有适合的商品"   ← 不再硬推耳机
```

**零词表、零字面规则**——所有判断都来自向量距离。

> 一个容易忽略的细节：**阈值只由"真正进入候选集"的商品决定。**
> 如果直接用召回里最接近的那个算 `best`，被预算/库存剔除的商品——
> 或者已删除但索引残留下来的幽灵向量——就会主导"什么叫近"。
> 实测过一个极端例子：幽灵向量距离 0.10，真实商品 0.31，
> 以 0.10 为基准算出的 cutoff=0.18 会把所有真实商品判为"太远"，
> 然后给用户一句错得离谱的"不符合预算条件"。

> 这里体现的是 RAG 的边界：**向量负责"找像的"，"像到什么程度算相关"交给标定过的阈值。**



---

## 实测数据

### 检索性能

| 操作 | 耗时 |
|---|---|
| MySQL LIKE 查名字 | **0.13 ~ 0.73 ms** |
| MySQL FULLTEXT（ngram） | 0.14 ~ 1.62 ms |
| RAG 检索（bge-m3 + Chroma） | **约 230 ms**（嵌入 156 ms + 检索 76 ms） |
| 索引构建 | 约 230 ms / 条 |
| 新增商品（含 LLM 打标） | 约 17 s（两个模型换入换出，见已知局限） |

### 语义召回效果（10 个真实商品）

| 查询 | 召回结果 |
|---|---|
| 能听歌的 | AirPodsPro, iPadAir, 12 |
| 适合办公的 | MacBookAirM3, 罗技鼠标M590, 机械键盘K8 |
| 跑步运动戴的 | AirPodsPro, 小米手环8 |
| 出差充电用的 | MacBookAirM3, 罗技鼠标M590, 充电宝20000mAh |
| 送礼 | iPhone15, 充电宝20000mAh |
| 今天天气怎么样 / 帮我订机票 / 你是谁 / asdfghjkl | **全部 0 条（被阈值拦截）** |

### 阈值标定（cosine 距离）

```
相关查询： 0.204 ~ 0.527
无关查询： 0.539 ~ 0.690
阈值 0.53 卡在两者之间，但间隙只有约 0.01~0.02。
```

---

## 快速开始

### 1. 准备环境

需要：**MySQL 8.0**、**Ollama**、**Python 3.12**、**Node.js + npm**。

```bash
ollama pull qwen2.5:7b        # 约 4.4 GB，工具调用与打标
ollama pull bge-m3            # 约 1.2 GB，向量嵌入
ollama serve
```

### 2. 建数据库

```bash
mysql -u root -p -e "CREATE DATABASE nlpilot CHARACTER SET utf8mb4;"
mysql -u root -p nlpilot < database/init.sql
```

> 如果 `product_lists` 还没有 `category / tags / description` 三列，需要先补：
> ```sql
> ALTER TABLE product_lists
>   ADD COLUMN category    VARCHAR(32)  DEFAULT NULL,
>   ADD COLUMN tags        VARCHAR(255) DEFAULT NULL,
>   ADD COLUMN description TEXT         DEFAULT NULL;
> ```

### 3. 配置环境变量

```bash
cd backend
copy .env.example .env        # Linux/macOS: cp
```

编辑 `backend/.env`，**至少改密码**：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=nlpilot

OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b

FLASK_PORT=5001
FLASK_DEBUG=true
```

### 4. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

首次启动会自动建向量索引，正常输出：

```
[自检] ✅ 10/10 个商品都有描述，语义检索完整
 * Running on http://0.0.0.0:5001
```

验证：

```bash
curl http://127.0.0.1:5001/api/health
# {"data_quality":{"products":10,"with_description":10},"rag":{"ok":true,"vectors":10},...}
```

**如果自检提示有商品缺描述**，跑一次补标：

```bash
cd backend && python scripts/auto_tag.py
```

### 5. 启动前端

```bash
cd frontend
npm install
npm start
```

打开 **http://localhost:4200**。跑测试用 `npm test`。

> 前端请求地址写死在 `frontend/src/app/services/api.service.ts` 的 `private base`，
> 改了后端端口要同步改这里。

---

## 项目结构

```
NLPilot - Smart Admin/
├── backend/
│   ├── app.py                     # Flask 入口 + 启动自检 + /api/health
│   ├── config.py                  # 读 .env
│   ├── db.py                      # DBUtils 连接池 + Transaction 事务上下文
│   ├── response.py                # 统一响应格式（HTTP 状态码 = 业务码）
│   ├── dao/                       # 数据访问层（SQL 全参数化）
│   │   ├── product_dao.py         #   商品 CRUD + save_enrichment + get_by_ids
│   │   ├── sales_dao.py           #   销售记录（支持借用连接/游标）
│   │   └── purchases_dao.py       #   进货记录（同上）
│   ├── services/
│   │   ├── nlu_service.py         #   调 Ollama 选工具 + 3 次重试 + 泄漏检测
│   │   ├── product_service.py     #   分发工具 + 商品名解析（精确 → LIKE）
│   │   ├── guard_service.py       #   结构判定：这次有没有真的执行
│   │   ├── tools.py               #   11 个工具（含事务 + 行锁 + 推荐）
│   │   ├── enrich_services.py     #   LLM 打标：品类 / 标签 / 描述
│   │   └── rag_services.py        #   向量库：_doc / upsert / search / delete
│   ├── routes/                    # 接口层
│   │   ├── chat_routes.py         #   /api/chat、/api/chat/confirm（双通道响应）
│   │   ├── product_routes.py      #   /api/products
│   │   ├── sales_routes.py        #   /api/sales
│   │   └── purchases_routes.py    #   /api/purchases
│   ├── scripts/
│   │   └── auto_tag.py            # 批量补标（同步 MySQL + 向量库）
│   └── prompts/system_prompt.py   # 系统提示词
├── frontend/src/app/
│   ├── app.routes.ts              # 4 个路由：chat / products / sales / purchases
│   ├── services/api.service.ts
│   ├── models/product.model.ts
│   └── components/                # chat / product-list / sales-list / purchases-list / navbar
├── database/init.sql              # 建表脚本
├── docs/
│   ├── architecture-v3.html       # 架构全景图（交互式，推荐）
│   └── architecture-v3.png        # 静态预览
└── README.md
```

---

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 + 数据质量 + 向量库状态 |
| GET | `/api/products?name=` | 查询商品（`name` 模糊匹配，可省略） |
| POST | `/api/products` | 新增商品 `{name, price, stock}`（自动打标） |
| PUT | `/api/products/<name>` | 修改 `{price?, stock?}` |
| DELETE | `/api/products/<name>` | 删除商品（同步删除向量） |
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

前端 `chat.ts` 的 `_handleError` 按 HTTP 状态码分类提示，所以后端必须返回真实状态码。

**`/api/chat` 的 `is_rag` 字段**标识这次结果是否来自语义召回：

```json
{ "ok": true, "count": 1, "is_rag": true,
  "data": [{ "id": 2, "name": "AirPodsPro", "price": "1899.00", "stock": 80 }] }
```

---

## 已知局限

### 🟠 影响体验

| 问题 | 说明 |
|---|---|
| **新增商品约 17 秒** | 打标调 qwen2.5:7b、建索引调 bge-m3，两个模型来回换入换出。给 Ollama 调用加 `keep_alive` 可降到 1~2 秒 |
| **阈值很脆** | 相关 ≤0.527、无关 ≥0.539，间隙只有 0.01~0.02，偶尔误召或漏召 |
| **RAG 只返回 top_k=3** | 语义召回固定取前 3 条，需要更多要靠结构化查询 |
| **`category` 值不规范** | LLM 会漂移出"鼠标""充电宝""平板电脑"，导致 `WHERE category='配件'` 查不到 |

### 🟡 功能缺口

| 问题 | 说明 |
|---|---|
| `category` 值是自由文本 | LLM 会打成"鼠标""充电宝""平板电脑"，精确匹配会漏，因此查询用 `LIKE` 兜住复合值 |
| 商品名含 `/` 无法改删 | 路由 `/api/products/<name>` 不匹配斜杠 |
| 无分页 / 无 `LIMIT` | 500 条销售记录会一次全返回 |
| 对话不持久化 | `conversations` / `messages` 表建了但零引用，刷新即丢 |
| 进货页文案是复制的 | `purchases-list.html` 标题写"销售记录"，selector 与销售页相同 |
| 测试覆盖低 | 前端仅 1 个 spec，后端无自动化测试；`test_pool.py` 是实验残留 |

---

## 从 v2 到 v3.1：变化清单

v2（`988bb98`）是一个"能用 Function Calling 增删改查"的 demo。
v3.1 在它之上做了三件事：**接入向量检索、补齐数据完整性、重做幻觉防护。**

### 一、数据与检索

| 维度 | v2 | v3.1 |
|---|---|---|
| 商品表字段 | `id / name / price / stock` | **+ `category` / `tags` / `description`** |
| 标签来源 | 无 | LLM 离线打标（`enrich_services` + `scripts/auto_tag.py`） |
| 语义检索 | 无 | **有，但只用两处**：查询兜底、推荐召回 |
| 索引维护 | 无 | 增删商品自动同步；启动全量重建；`auto_tag.py` 批量补标时同步 |
| 集合查询 | 只能按名字 | **+ 品类 / 价格区间 / 是否有货 / 排序**（SQL，0.13~0.73ms） |

> **关键取舍**：向量不是"什么都能干"。精确查询和结构化筛选一律走 SQL——
> 实测 200 个商品时 SQL 比向量快 **343~2628 倍**。

### 二、推荐能力（v2 完全没有）

| 维度 | v2 | v3.1 |
|---|---|---|
| 推荐工具 | ❌ 没有，"推荐个礼物"会追问或返回全部 | ✅ `recommend_products(occasion, budget, top_k)` |
| 候选来源 | — | 向量宽召回 top10（阈值 0.75） |
| 过滤 | — | 预算 + 库存硬过滤 |
| 排序 | — | 纯向量距离（零词表、零字面规则） |
| 兜底 | — | 相对阈值 `best + 0.08`；`best > 0.55` 时如实说"库里没有" |
| 理由 | — | 每个结果附 `reason`（取自描述，零延迟） |

**踩过的坑**：第一版是"纯向量 + 取前 3"，问"送女朋友礼物"推出了机械键盘。
查真实距离才发现 10 个商品全挤在 0.45~0.58，阈值形同虚设——
**向量负责"找像的"，"像到什么程度算相关"要靠标定过的阈值。**

中间试过两条路，都放弃了：
- **同义词表 + 字面打分**：能用，但是穷举（18 个键 / 60 个词，永远补不完）
- **HyDE（让模型扩写成理想商品再检索）**：小语料上更差——模型扩成"施华洛世奇手链"，
  而库里没有手链，向量落到语料分布之外，最近邻全是噪声

### 三、幻觉防护（改动最大）

| 维度 | v2 | v3.1 |
|---|---|---|
| 做法 | 关键词白名单（`SAFE_HINTS`，10 余条） | **通道分离**：`result`（工具）/ `reply`（对话） |
| 判定依据 | 用户消息里有没有安全词 | **有没有调用工具**（结构事实） |
| 代码量 | 逐步膨胀到约 190 条规则 / 197 行 | **49 行（34 行是注释）** |
| 同一批用例 | 10/11（会漏"只查不改却称改了"） | **11/11** |
| 前端 | 一个气泡，事实与话术混在一起 | 绿色结果卡片 / 气泡 + 「未执行」标记 |

**走过的弯路（值得写进报告）**：

1. 正则守卫：换个说法就漏（"已删除"→"已经帮你删掉了"→"帮你删好了"…）
2. 用 7B 当审核员：**无证据 45%（全判 pass）、带证据仅 55%**，还会把"用户请求"当成"已发生的事实"，
   且对提示词措辞高度敏感（同批用例从 0/6 变 3/6）
3. 结论：**真伪判断是语义任务，不该由规则承担，也不该让同一个模型自审**
4. 最终方案：不给模型记账权——副作用只走工具，结果只由工具返回值陈述

### 四、健壮性

| 问题 | v2 | v3.1 |
|---|---|---|
| 写操作 + 扣库存 | 两个 DAO 各自 commit，可能只成功一半 | **单事务**，失败整体回滚 |
| 并发超卖 | 读-判断-写之间有窗口 | **`SELECT ... FOR UPDATE` 行锁**（10 线程抢 5 库存，恰好成功 5 次） |
| 改价未变化 | `rowcount=0` 仍报"已更改" | 返回"价格已经是 X，未做修改" |
| 商品名不匹配 | `iphone` → "商品不存在" | **精确 → LIKE 对齐**，唯一命中自动纠正，多候选反问 |
| 数据完整性 | 无感知 | 启动自检 + `/api/health` 暴露描述覆盖率 |

### 五、工程细节

| 项 | v2 | v3.1 |
|---|---|---|
| 端口 | 5000 | **5001**（本机 5000 被其他程序占用，`127.0.0.1` 被劫持） |
| 依赖 | — | `chromadb` / `sentence-transformers` 链路（bge-m3） |
| 架构图 | 无 | `docs/architecture-v3.html`（交互式）+ PNG 预览 |
| 文档 | 594 行 | 约 850 行，含设计取舍与实测数据 |

### 一句话总结这三版

```
v2：能听懂人话，但只会"查名字"
v3.0：能理解意思了（RAG），但推荐会凑数、结果真假难辨
v3.1：把"更聪明"（工具表达力 + 推荐）和"更可信"（通道分离）分开做
```

---

## 版本历史

- **v0.1**：基础 CRUD + prompt + JSON 意图识别
- **v0.2**：Function Calling + 销售 / 进货模块
- **v0.3**：重试机制 + tool_call 泄漏检测 + 幻觉拦截（关键词白名单）
- **v0.4**：健壮性修复
  - 修复 `POST /api/sales` 缺 `name` 时的 500 崩溃
  - 修复 `PUT /api/products` 的 `stock` 校验恒真错误（曾导致改库存完全失效）
  - 补齐全部布尔值校验（`isinstance(x, bool)`）
  - `error()` 返回真实 HTTP 状态码，激活前端错误处理
  - 幻觉守卫改为 `SAFE_HINTS` + 默认不信任
- **v0.5**：事务与并发
  - 新增 `db.Transaction` 事务上下文管理器
  - DAO 支持借用外部连接 / 游标，事务边界上移到业务层
  - 「写记录 + 改库存」改为单事务，失败整体回滚
  - 库存读取加 `SELECT ... FOR UPDATE` 行锁，消除并发超卖
- **v3.0**：接入 RAG
  - 新增 `enrich_services`：LLM 自动生成品类 / 标签 / 描述
  - 新增 `rag_services`：ChromaDB 向量库 + bge-m3 嵌入
  - `query_products` 增加语义兜底（SQL 查空 → 向量召回 → 回查 MySQL）
  - 新增 / 删除商品自动同步索引；`scripts/auto_tag.py` 支持批量补标
  - 启动自检 + `/api/health` 暴露数据完整度
  - 新增架构全景图 `docs/architecture-v3.html`
- **v3.1（当前）**：把"更聪明"和"更可信"分开做
  - **工具表达力**：`query_products` 增加 `category` / `max_price` / `min_price` / `in_stock` / `sort`，
    工具描述写明使用场景与「不要把条件塞进 name」，修掉"500 块以内"被传成 `name="500块以内"`
  - **系统提示词**：参数已给出时不再反复追问（工具选择 11/14 → 14/14）
  - **新增 `recommend_products(occasion, budget, top_k)`**：语义宽召回 → 预算/库存过滤 → 贴合度排序 → 附理由，
    工具数 10 → 11，模型只需一次调用
  - **推荐两级选取** → 最终改为**纯向量 + 相对阈值**：绝对阈值 0.55、相对阈值 `best + 0.08`（实测标定），
    零词表、零字面规则；`best` 都超过 0.55 时如实说"库里没有适合的商品"（修掉"送女朋友礼物"推荐出机械键盘）
  - **修复 tool_call 泄漏导致整条请求失败**：qwen2.5 有时把 tool_call 当文本吐出来
    （`leton {"name": ...}</tool_call>`），三次重试内容相同。现在从泄漏文本里解析出 JSON 恢复调用，
    把失败变成成功；纯文字回复也不再白跑三次
  - **前端显示结果来源**：结果卡片区分「来自数据库（SQL）」与「语义召回（向量检索）」，
    让 RAG 到底在哪生效变得可见
  - **幻觉防护改为通道分离**：放弃约 190 条文本规则，响应拆 `result`（事实）/ `reply`（对话），
    `guard_service` 197 → 49 行，同批用例 10/11 → 11/11；并补 `/api/chat/confirm` 的 `rowcount == 0` 判断
  - **商品名解析**：写操作前按 精确 → LIKE 对齐名字（`iphone` → `iPhone15`），多候选则反问不猜
  - 端口 5000 → 5001（本机 5000 被其他程序占用）

---

## 后续计划

**近期（提升可用性）**

1. 给 Ollama 调用加 `keep_alive="30m"`，把新增从 17 秒降到 1~2 秒
2. 推荐结果接入图片与销量排序（目前只用标签/描述）
3. `category` 写入时归一化（别名映射），让精确匹配可用
4. 重新标定阈值（或改为"top-1 距离 + LLM 复核"两段式）

**中期（补质量）**

5. 补测试：事务回滚、布尔校验、幻觉守卫、RAG 阈值
6. 商品名含 `/` 改为请求体传名字
7. 查询接口加分页 `LIMIT`
8. 对话持久化（用上已有的 `conversations` / `messages` 表）

**远期（扩展能力）**

9. 知识库问答：退换货 / 物流 / 发票政策（RAG 的真正主场，独立于商品表）
10. 相似商品推荐（复用描述向量做 kNN）
11. 别名表（"苹果手机" → iPhone15），比 embedding 更精确可解释

---

## 常见问题

**Q：后端启动就崩，报 `Can't connect to MySQL server` / `OperationalError (2003)`**

`backend/db.py` 在**模块导入时**就用 `mincached=2` 建连接池，
所以 MySQL 没启动后端根本起不来，且报错栈全是连接池内部调用。
请先确认 MySQL 已启动、`.env` 密码正确。

**Q：对话报错或没反应**

Ollama 没启动，或模型没拉。检查：

```bash
curl http://127.0.0.1:11434/api/tags
ollama pull qwen2.5:7b && ollama pull bge-m3
```

**Q：启动自检提示"有商品缺描述"**

说明这些商品无法被语义检索到（只能按名字查）。跑一次补标：

```bash
cd backend && python scripts/auto_tag.py
```

脚本会同时更新 MySQL 和向量库。

**Q：AI 回"我没能理解你的操作意图，请换一种说法重试（未执行任何操作）"**

这是**幻觉守卫生效**，不是 bug。说明模型没有调用工具（可能想用文字请求确认，
或者不认得你的说法）。换更明确的说法即可：

| 被拦下的说法 | 换成 |
|---|---|
| "补 5 个 AirPodsPro" | "补货 AirPodsPro 5 个" |
| "帮我处理掉 AirPodsPro" | "删除 AirPodsPro" |
| "帮我把 iPhone15 价格降下来" | "把 iPhone15 价格改成 4799" |

**关键是这次操作绝对没有执行**——不会出现"以为卖掉了其实没卖"。

**Q：新增商品时名字里的空格消失了**

这是设计（统一 `replace(" ", "")`），为了让"用户输名字"和"数据库里存的名字"能精确匹配。
目前没有任何提示，属于已知问题。

**Q：重复执行 `database/init.sql` 报 `Table 'product_lists' already exists`**

该脚本里 `product_lists` / `conversations` / `messages` 三张表没有 `IF NOT EXISTS`。
重建请先 `DROP DATABASE nlpilot`。

**Q：`rag_store/` 目录要不要提交？**

不要。它是运行时生成的向量库，已由 `.gitignore` 忽略，启动时会按 MySQL 现状自动重建。
