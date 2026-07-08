# B站新能源汽车发布会监控实战清单

## 1. 目标

今天的目标不是一次性做全量分析，而是先稳定跑通一场 B站 新能源汽车发布会的基础监控链路：

- 成功进入直播间
- 持续抓取弹幕
- 持续记录热度快照
- 能在直播结束后拿到原始数据库结果

当前项目已经具备 B站 MVP 采集能力，适合先完成以下 P0 指标：

- 热度表现
  - 峰值热度值
  - 平均热度值
- 互动表现
  - 弹幕总量
  - 弹幕人数
  - 弹幕密度
- 内容口碑
  - 原始弹幕文本留存，供后续情感分析和关键词分析

说明：

- 当前 B站 采集器抓到的 `online_count` 更接近页面展示的人气值，不一定等于平台真实在线人数。
- 当前 `like_count` 仍为 `0`，今天先不作为核心交付指标。

---

## 2. 开播前准备

### 2.1 环境确认

在项目根目录执行：

```bash
./venv/bin/python main.py --help
./venv/bin/python main.py init-db
```

当前项目已支持在 SQLite 路径父目录不存在时自动创建目录，因此默认数据库初始化应可直接成功。

### 2.2 确认房间号

B站 直播间房间号一般来自直播链接，例如：

```text
https://live.bilibili.com/12345678
```

其中 `12345678` 就是 `room_id`。

如果页面是活动页或短链，优先在浏览器打开后确认最终落地的直播间地址。

### 2.3 明确任务元信息

建议在启动前先确定两项元信息，避免后续数据混乱：

- `event_name`
  - 例如：`2026 某品牌新车发布会`
- `car_brand`
  - 例如：`xiaomi`、`byd`、`nio`、`xpeng`

建议统一使用英文或固定拼音，方便后续筛选。

---

## 3. 启动命令

推荐今天优先使用有头模式，便于观察页面是否正常加载：

```bash
./venv/bin/python main.py start bilibili <room_id> --event-name "2026 某品牌新车发布会" --car-brand "品牌名" --headed
```

示例：

```bash
./venv/bin/python main.py start bilibili 12345678 --event-name "2026 某品牌新车发布会" --car-brand "xiaomi" --headed
```

如果后续确认稳定，再切到无头模式：

```bash
./venv/bin/python main.py start bilibili <room_id> --event-name "2026 某品牌新车发布会" --car-brand "品牌名"
```

---

## 4. 开播中巡检要点

### 4.1 终端应看到的正常日志

正常情况下，终端会出现类似输出：

```text
[bilibili] 成功进入直播间: 12345678
[bilibili] 抓取到 12 条新弹幕
[bilibili] 成功将 24 条弹幕写入数据库，当前热度: 356000
```

如果持续能看到这三类信息，说明今天的基础监控链路是通的。

### 4.2 人工巡检频率

建议至少每 5 到 10 分钟检查一次：

- 浏览器页面是否还停留在直播间
- 终端是否仍有新增弹幕日志
- 是否出现页面结构变更或超时异常

### 4.3 建议人工记录的关键时间点

今天即使不做自动事件识别，也建议人工记下几个时间点，方便赛后复盘：

- 开播时间
- 核心车型亮相时间
- 价格公布时间
- 权益公布时间
- 智驾或续航重点讲解时间
- 结束时间

这些时间点后续可以和弹幕密度、热度波动做对应分析。

---

## 5. 直播结束后

### 5.1 正常停止

在终端按 `Ctrl+C` 结束采集。

当前实现会在停止时尝试关闭浏览器并结束任务状态；如果缓冲区里还有未写入弹幕，也会在退出前做一次落库。

### 5.2 快速检查数据库里是否有数据

可以执行下面的 Python 片段做最小验证：

```bash
./venv/bin/python - <<'PY'
from app.core.database import SessionLocal
from app.models.schema import EventTask, DanmakuRecord, LiveMetric

db = SessionLocal()
try:
    print("tasks =", db.query(EventTask).count())
    print("danmakus =", db.query(DanmakuRecord).count())
    print("metrics =", db.query(LiveMetric).count())
finally:
    db.close()
PY
```

如果这三项都大于 `0`，说明今天的基础采集结果已经成功落盘。

### 5.3 快速导出赛后统计

如果你想在发布会结束后立刻看基础结果，可以直接执行：

```bash
./venv/bin/python scripts/post_event_summary.py
```

默认会读取最近一场任务，并输出：

- 弹幕总量
- 独立发言用户数
- 热度峰值
- 峰值出现时间
- 平均热度
- 热度采样时间范围

如果要指定某一场任务，可以使用以下方式：

```bash
./venv/bin/python scripts/post_event_summary.py --task-id 3
./venv/bin/python scripts/post_event_summary.py --event-name "2026 某品牌新车发布会"
./venv/bin/python scripts/post_event_summary.py --room-id 12345678
```

如果后续要接自动化流程或导出到别的脚本里，可以使用 JSON 输出：

```bash
./venv/bin/python scripts/post_event_summary.py --json
```

---

## 6. 今天建议关注的指标

结合当前项目能力，今天优先看以下结果：

- 热度类
  - 热度峰值
  - 热度均值
  - 热度峰值出现时间附近的弹幕内容
- 互动类
  - 弹幕总量
  - 独立发言用户数
  - 每分钟弹幕密度
- 内容类
  - 价格相关讨论
  - 智驾相关讨论
  - 续航相关讨论
  - 竞品提及
  - 明显正向和负向弹幕样本

如果今天只做一场试跑，重点不是评分模型，而是先验证采集连续性和数据可用性。

---

## 7. 当前已知限制

今天这版 B站 采集器属于 MVP，已知限制如下：

- 采集方式是 DOM 解析，不是 WebSocket 原始消息解析
- `online_count` 采的是页面展示热度值，不能直接当绝对在线人数使用
- `like_count` 还没有落地
- 只有当缓冲区达到一定数量时才会批量写库，因此低弹幕场景下写库频率会偏低
- 页面 DOM 结构如果变更，选择器可能失效

因此今天的目标应定义为：

- 跑通一场真实发布会监控
- 沉淀可复盘的原始弹幕数据
- 确认 B站 作为第一阶段平台可稳定落地

---

## 8. 异常排查

### 8.1 数据库初始化失败

先执行：

```bash
./venv/bin/python main.py init-db
```

如果仍失败，检查环境变量 `DATABASE_URL` 是否被外部覆盖。

### 8.2 能打开页面但没有弹幕

优先检查：

- 当前房间是否真正开播
- B站 页面结构是否有变化
- 弹幕区是否仍然存在 `#chat-history-list`

建议改用 `--headed` 模式肉眼观察页面。

### 8.3 有弹幕日志但热度始终为 0

这通常说明热度选择器没有命中，需要重新检查 B站 页面上的热度展示节点。

### 8.4 程序中途中断

优先保留终端报错信息，不要直接重开多次。先确认是：

- 网络问题
- 页面结构问题
- 浏览器被风控或页面卡死

---

## 9. 今天的推荐执行顺序

1. 确认直播链接和 `room_id`
2. 执行 `init-db`
3. 用 `--headed` 启动 B站 监控
4. 开播前观察页面是否正常进入
5. 开播后每 5 到 10 分钟做一次人工巡检
6. 记录关键发布时间点
7. 直播结束后 `Ctrl+C` 停止
8. 检查 `event_tasks`、`danmaku_records`、`live_metrics` 是否有数据

如果这 8 步全部跑通，今天就算完成了 B站 新能源汽车发布会的技术准备和实战验证。
