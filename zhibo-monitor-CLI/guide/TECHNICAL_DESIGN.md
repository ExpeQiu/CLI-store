# 新能源车企发布会直播监控中台 —— 技术方案与可行性论证

## 1. 核心架构与技术栈选型

根据前期的沟通，我们确定了以 **Python** 为主语言，**MySQL/PostgreSQL** 为核心存储的基调。以下是详细的组件选型：

| 模块 | 技术选型 | 选型理由 |
| --- | --- | --- |
| **CLI 框架** | `Typer` (基于 Click 和 Pydantic) | 语法现代，自动生成帮助文档，类型提示友好，非常适合快速构建功能丰富的命令行工具。 |
| **并发与网络** | `asyncio` + `aiohttp` / `websockets` | 弹幕采集是典型的高并发 I/O 密集型任务，异步协程能单机承载多平台的并发连接。 |
| **反爬与数据抓取** | `Playwright` + `mitmproxy` (备选) | 许多平台（如抖音、视频号）的弹幕通过 WSS (WebSocket Secure) 加密传输或 protobuf 序列化。Playwright 可以直接驱动无头浏览器截获前端解密后的数据，降低逆向工程成本。 |
| **NLP 分析** | `Jieba` (分词) + LLM API (如 DeepSeek/智谱等) | 汽车圈黑话（如“背刺”、“工业垃圾”、“遥遥领先”）传统情感分析模型极易误判。接入低成本大模型 API 进行批量判定，准确率远高于传统方案。 |
| **数据存储** | `PostgreSQL` + `SQLAlchemy` (ORM) | PostgreSQL 对 JSONB 格式支持极佳，初期可以将非结构化的弹幕原文存为 JSON，同时利用关系型表存储聚合后的分钟级指标。MVP 阶段单机可承载千万级弹幕。 |
| **BI 与报表** | `Metabase` / `Apache Superset` | 开源 BI 工具，直连 PostgreSQL，拖拽式生成“弹幕密度曲线”、“情感雷达图”、“高频词云”，无需开发复杂的前端页面。 |

---

## 2. 数据流转架构设计

数据从产生到展现的生命周期分为 4 步：

1. **采集端 (Ingestion)**: 
   - `zhibo-monitor start douyin <room_id>`
   - 启动 Playwright 进程，进入直播间，通过 `page.on('websocket')` 监听并解析弹幕和热度数据。
2. **缓冲与聚合 (Buffering & Aggregation)**:
   - 考虑到发布会高潮期可能有几千条/秒的弹幕，直接写库会导致数据库锁死。
   - 引入 **内存缓冲池 (Memory Buffer)** 或轻量级队列 (如 Python `asyncio.Queue`)，每 5 秒或满 1000 条进行一次批量 Insert (Batch Insert)。
3. **清洗与 NLP (Processing)**:
   - 旁路任务或离线任务：`zhibo-monitor analyze <task_id>`。
   - 提取最新采集的弹幕 -> 过滤无意义刷屏 -> 按分钟打包发给 LLM API -> 返回 {情感极性: 正向, 关键词: ["价格", "续航"]} -> 写回数据库。
4. **存储与展现 (Storage & BI)**:
   - 数据沉淀在 `livestream_metrics` (分钟级热度) 和 `danmaku_records` (弹幕明细) 表中。BI 工具定时刷新大屏。

---

## 3. 关键难点与可行性论证 (可行性风险评估)

### 难点 1：多平台数据协议不一与反爬虫策略
* **业务挑战**：抖音、B站、视频号、微博的直播间协议完全不同，且抖音/视频号的反爬策略极严（如签名校验、风控弹窗）。
* **论证与应对**：
  - 不走纯协议逆向（维护成本极高，随时失效）。
  - **采用“降维打击”**：使用 `Playwright` 自动化框架开启真实浏览器。直接拦截 WebSocket 帧，或者直接通过 DOM 树读取渲染后的弹幕。DOM 读取虽然性能略有损耗，但 100% 绕过协议加密，对于 MVP 阶段最为稳妥。

### 难点 2：高并发弹幕的写入性能瓶颈
* **业务挑战**：热门发布会（如小米 SU7 发布会）同时在线人数达百万，弹幕并发极高。MySQL/PG 若每条弹幕单次 Insert，TPS 瞬间被打满。
* **论证与应对**：
  - 必须采用**批量插入 (Bulk Insert)**。在应用层设立缓冲队列，每 1 秒或 500 条合并成一条 SQL 执行。
  - 对于 MVP，PostgreSQL 配合批量写入，单机万级 TPS 完全可行，无需过早引入 Kafka 或 ClickHouse。

### 难点 3：汽车行业黑话与情感分析的准确性
* **业务挑战**：“这价格，小米背刺老车主啊”、“底盘像开船一样”——这类句式传统词典匹配法无法准确判断褒贬。
* **论证与应对**：
  - 放弃传统的 SnowNLP 或通用情感模型。
  - **微批处理 + 大模型 API**：利用 DeepSeek-V3 或 智谱 GLM-4 等 API（目前价格极低），通过精心的 Prompt（提示词）设计，每次传入 50 条弹幕，让大模型返回结构化 JSON 评价。不仅能判断正负面，还能直接归类到“价格”、“外观”、“智驾”等维度。

---

## 4. 评价体系的数据模型 (核心表结构设计)

为了支撑最终的“发布会战力指数”，我们需要以下几张核心表：

1. **`event_tasks` (发布会任务表)**
   - `task_id`, `car_brand`, `event_name`, `platform`, `room_id`, `start_time`, `end_time`
2. **`live_metrics` (热度时序表 - 分钟级)**
   - `id`, `task_id`, `timestamp`, `online_count` (在线人数), `like_count` (点赞数), `danmaku_density` (当分钟弹幕量)
3. **`danmaku_records` (弹幕明细表)**
   - `id`, `task_id`, `timestamp`, `user_name`, `user_id` (用户ID), `user_level` (用户等级), `content` (弹幕内容)
4. **`danmaku_analysis` (弹幕 NLP 分析表)**
   - `id`, `danmaku_id` (关联明细表), `task_id`, `sentiment_score` (-1.0 到 1.0), `intent_score` (购买意向 0-10), `keywords` (JSON数组，如 `["底盘", "舒适"]`)
5. **`interaction_events` (特殊互动事件表)**
   - `id`, `task_id`, `timestamp`, `user_name`, `gift_name`, `gift_value`

---

## 5. 阶段实施计划 (Roadmap)

建议分三个阶段进行开发：

* **Phase 1: 数据采集 MVP (验证抓取可行性)**
  - 搭建 CLI 框架。
  - 跑通 1 个平台（建议先从 B站 或 抖音 开始）的直播间弹幕与热度抓取。
  - 将数据成功落盘到本地 SQLite 或 PostgreSQL。
* **Phase 2: 分析与评价引擎 (验证 NLP 效果)**
  - 接入 LLM API 进行批量弹幕清洗与打标。
  - 制定权重，利用 SQL 算出“热度指数”、“互动指数”和“情感指数”。
* **Phase 3: 数据看板与多平台扩展**
  - 搭建 BI 看板（Metabase）。
  - 横向扩展对视频号、微博直播的支持。