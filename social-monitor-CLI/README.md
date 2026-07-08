# social-monitor

轻量级社交媒体监控命令行工具，支持微博、微信公众号、小红书、抖音、B站、知乎数据采集。

## 安装

```bash
pip install -e .
# 或
pip install -r requirements.txt
pip install -e .
```

## 快速开始

```bash
# 初始化配置
social-monitor config init

# 微博用户动态
social-monitor fetch weibo --uid 1974576991 --pages 5

# 微博热搜
social-monitor fetch weibo-trending --count 20

# 抖音热榜
social-monitor fetch douyin-trending

# B站 UP 主视频
social-monitor fetch bilibili --uid 614946423

# B站排行榜
social-monitor fetch bilibili --type ranking

# B站视频弹幕
social-monitor fetch bilibili-danmaku --bvid BV1xx411c7mD

# B站弹幕高频词
social-monitor fetch bilibili-danmaku --bvid BV1xx411c7mD --words --top 30

# B站直播弹幕（需 pip install 'social-monitor[live]'）
social-monitor fetch live-danmaku --room-id 22603245 --duration 60
social-monitor fetch live-danmaku --room-id 22603245 --words --top 20

# 知乎热榜
social-monitor fetch zhihu-trending

# 保存到本地 PostgreSQL（需先 docker compose up -d）
social-monitor fetch weibo-trending --save
```

## 配置

配置文件路径：`~/.social-monitor/config.yaml`

Cookie 优先级：`--cookie` > 环境变量 > `cookies/*.txt` > config.yaml

```bash
# 小红书推荐：浏览器登录（自动签名）
pip install 'social-monitor[browser]'
playwright install chromium
social-monitor config login xiaohongshu
social-monitor config check xiaohongshu

# 或手动保存 Cookie
social-monitor config cookie set xiaohongshu --value "a1=xxx; web_session=xxx"

# 检测所有平台
social-monitor config check all

# 情报采集：批量热榜 + 增量
social-monitor intel trending --diff --notify
social-monitor fetch weibo-trending --save --diff   # 仅输出新增热搜
```

参考 `config.yaml.example`。

## 情报采集

```bash
# 每天 cron 跑一次，自动对比历史、飞书通知新增
social-monitor intel trending --diff --notify

# 单平台增量
social-monitor fetch zhihu-trending --save --diff
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `fetch weibo` | 微博用户动态 |
| `fetch weibo-trending` | 微博热搜 |
| `fetch wechat` | 微信公众号（需 RSSHub） |
| `fetch xiaohongshu` | 小红书笔记（需 Cookie） |
| `fetch douyin-trending` | 抖音热榜 |
| `fetch douyin` | 抖音用户视频 |
| `fetch bilibili` | B站视频/排行榜 |
| `fetch bilibili-danmaku` | B站视频弹幕/高频词 |
| `fetch live-danmaku` | 直播弹幕（B站，需 `[live]` 扩展） |
| `fetch zhihu-trending` | 知乎热榜 |
| `fetch zhihu-answers` | 知乎问题回答 |
| `notify feishu` | 飞书通知 |
| `config init/show` | 配置管理 |
| `config check` | Cookie / 连通性检测 |
| `config login` | 浏览器登录（小红书） |
| `config cookie set` | 保存 Cookie 文件 |
| `intel trending` | 批量热榜 + 增量对比 |

## 验证

```bash
./verify.sh
```
