# 新能源车企发布会直播监控与分析数据中台

## 1. 系统架构设计 (Data Mid-end Architecture)

### 1.1 数据采集层 (Data Acquisition)
- **核心目标**: 实时/离线获取主流平台（抖音、B站、视频号、微博等）的直播数据。
- **采集指标**:
  - **基础流量**: 在线人数（峰值PCU、平均ACU）、累计观看人次。
  - **互动数据**: 弹幕内容、弹幕发送者等级、点赞数、礼物价值。
  - **流媒体状态**: 直播推流稳定性、画质参数（可选）。
- **工具形态**: 基于 `zhibo-monitor-CLI` 提供统一的命令行调度工具。

### 1.2 数据处理层 (Data Processing)
- **数据清洗**: 过滤重复弹幕、水军刷屏、无效符号。
- **NLP分析**: 
  - 情感分析：判断弹幕是正向（如“遥遥领先”、“价格真香”）、中性还是负向（如“太贵了”、“外观丑”）。
  - 实体识别：提取竞品提及（如在极氪直播间提到小米）、核心卖点提及（如“智驾”、“续航”、“空间”）。
- **实时计算**: 统计每分钟的弹幕密度、情感波动曲线。

### 1.3 数据存储层 (Data Storage)
- **时序数据**: InfluxDB / Prometheus (存储每秒/每分钟的在线人数、互动量)。
- **文档数据**: MongoDB / Elasticsearch (存储海量弹幕原文和NLP分析结果，便于全文检索)。
- **关系型数据**: PostgreSQL / MySQL (存储发布会元数据、最终统计报表、平台账号信息)。

### 1.4 多维度分析与展现层 (BI & Visualization)
- **看板工具**: Apache Superset / Metabase / 甚至自建前端大屏。

---

## 2. 发布会评价体系 (Evaluation System)

建立一套**“发布会综合战力指数” (Launch Event Power Index, LEPI)**，由以下四个维度加权计算：

1. **热度指数 (30%)**
   - 峰值在线人数 (PCU)
   - 累计观看人次
   - 平均停留时长
2. **互动指数 (30%)**
   - 弹幕总数 / 弹幕密度 (条/分钟)
   - 互动率 (发弹幕人数 / 总观看人数)
   - 礼物与点赞总数
3. **口碑与情感指数 (25%)**
   - 正向情感弹幕占比
   - 核心卖点（如“智驾”、“价格”）的讨论热度与正向反馈率
   - 竞品提及率（负向扣分或对比分析）
4. **转化意向指数 (15%)**
   - 弹幕中“买”、“下定”、“冲”等高意向词汇频次
   - 官方留资链接的点击/转化率（需结合车企内部数据或通过特定口令统计）

---

## 3. zhibo-monitor-CLI 规划

作为整个中台的数据抓取与调度入口，`zhibo-monitor-CLI` 将包含以下功能：
- `zhibo-monitor login <platform>`: 用于强制扫码登录的平台（如视频号 sph），持久化登录态。
- `zhibo-monitor start <platform> <room_id>`: 启动某个直播间的实时监控。
- `zhibo-monitor ingest`: 接收 `screen-watch` JSONL 管道，写入数据库（platform=`sph-client`）。
- `zhibo-monitor status`: 查看当前正在监控的直播任务。
- `zhibo-monitor export <room_id>`: 导出某场发布会的原始数据。
- `zhibo-monitor analyze <room_id>`: 触发本地 NLP 情感分析和报表生成。

---

## 4. 开发进度 (Development Progress)

### 4.1 数据采集层支持情况
| 平台 | 状态 | 备注 |
| --- | --- | --- |
| 抖音 (Douyin) | ✅ 已验证 | 已完成核心数据（弹幕、在线人数等）的抓取验证 |
| B站 (Bilibili) | ✅ 已验证 | 已完成核心数据（弹幕、在线人数等）的抓取验证 |
| 视频号 (WeChat Channels) | ✅ 已验证 | 已支持基于 Playwright DOM 解析的弹幕与热度采集（需扫码登录） |
| 视频号客户端 (sph-client) | ✅ 已支持 | 通过 `screen-watch` OCR 管道 + `zhibo-monitor ingest` 入库 |
| 微博 (Weibo) | ✅ 已验证 | 已支持基于 Playwright DOM 解析的采集，支持扫码登录持久化 |

### 4.2 Phase 2 优化与分析架构
- **表结构动静分离**: 拆分 `danmaku_records` 与 `danmaku_analysis`，便于独立接入大模型 API 进行情感和实体分析。
- **高并发写入优化**: 在爬虫基类 (`BaseScraper`) 引入内存缓冲队列（Buffer Queue），实现批量落库（Batch Insert），缓解 SQLite/PostgreSQL 在高潮期的写入锁冲突。
- **用户画像补全**: 模型中已支持 `user_id` 与 `user_level`（粉丝牌）等字段的记录，为后续计算粉丝互动率与黏性提供数据支撑。

