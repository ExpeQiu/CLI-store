# social-monitor CLI 技术方案

> **编制日期**：2026-06-16
> **版本**：v1.0
> **编制主体**：超级作战队
> **状态**：技术方案设计，待开发

---

## 一、产品定位

### 1.1 核心定位

**轻量级社交媒体监控命令行工具**，用于快速采集公开可见的社交媒体数据。

### 1.2 与 Octopus 的分工

| 维度 | Octopus CLI | social-monitor CLI |
|------|-------------|-------------------|
| **定位** | 主力、模板化、复杂页面 | 轻量、快速、API直连 |
| **启动方式** | Chrome 浏览器自动化 | Python 脚本直接请求 |
| **适用场景** | 复杂页面、多字段、批量 | 简单页面、公开API、高频轮询 |
| **部署** | 需要八爪鱼账号 | 纯开源、零成本 |
| **数据量** | 大规模采集 | 中小规模采集 |

### 1.3 设计原则

- **零依赖**：除标准库外，尽量少用第三方库
- **零配置启动**：内置默认参数，指定账号即可运行
- **JSON优先**：所有输出默认为 JSON，便于程序解析
- **可观测**：详细的日志输出，方便调试

---

## 二、技术架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      social-monitor CLI                       │
├─────────────────────────────────────────────────────────────┤
│  cli.py (Click 主入口)                                      │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  platforms/  │   storage/   │ notifiers/   │    utils/      │
│  平台采集器   │    存储层    │   通知层     │    工具层      │
├──────────────┼──────────────┼──────────────┼────────────────┤
│  weibo.py    │ postgres.py │ feishu.py    │ http_client.py │
│  wechat.py   │ json_file.py│             │ cookie_mgr.py  │
│  xiaohongshu.py│           │             │ scheduler.py   │
│  douyin.py   │             │             │ rate_limiter.py│
│  bilibili.py │             │             │                 │
│  zhihu.py    │             │             │                 │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

### 2.2 项目结构

```
social-monitor/
├── social_monitor/
│   ├── __init__.py
│   ├── __version__.py              # 版本信息
│   ├── cli.py                      # Click 主入口
│   ├── config.py                   # 配置管理
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py               # 平台基类
│   │   ├── weibo.py              # 微博
│   │   ├── wechat.py             # 微信公众号
│   │   ├── xiaohongshu.py        # 小红书
│   │   ├── douyin.py             # 抖音
│   │   ├── bilibili.py           # B站
│   │   └── zhihu.py              # 知乎
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py               # 存储基类
│   │   ├── postgres_storage.py   # PostgreSQL 存储（默认）
│   │   ├── mysql_storage.py      # MySQL 存储（可选）
│   │   └── json_storage.py       # JSON 文件存储（可选）
│   ├── notifiers/
│   │   ├── __init__.py
│   │   └── feishu.py             # 飞书通知
│   └── utils/
│       ├── __init__.py
│       ├── http_client.py         # HTTP 客户端
│       ├── cookie_manager.py      # Cookie 管理
│       ├── rate_limiter.py        # 频率限制
│       └── logger.py              # 日志工具
├── tests/
├── requirements.txt
├── setup.py
├── README.md
├── CHANGELOG.md
└── config.yaml.example
```

---

## 三、平台实现方案

### 3.1 微博（weibo.py）

**数据来源**：微博搜索/用户主页（无需登录版）

**依赖**：
- `requests` 或标准库 `urllib`
- 免费接口：`https://m.weibo.cn/api/container/getIndex`

**实现思路**：

```python
# 微博用户主页 API（无需登录）
# URL: https://m.weibo.cn/api/container/getIndex?uid={uid}&type=user

class WeiboCollector(BaseCollector):
    """微博采集器"""
    
    BASE_URL = "https://m.weibo.cn/api/container/getIndex"
    
    def fetch_user_timeline(self, uid: str, max_page: int = 10) -> List[Dict]:
        """获取用户最新微博"""
        cards = []
        for page in range(1, max_page + 1):
            params = {
                "uid": uid,
                "type": "user",
                "containerid": f"107603{uid}",
                "page": page
            }
            resp = self.http_client.get(self.BASE_URL, params=params)
            data = resp.json()
            
            cards.extend(data.get("data", {}).get("cards", []))
            
            # 频率控制：每页间隔 2-3 秒
            time.sleep(random.uniform(2, 3))
        
        return self._parse_cards(cards)
    
    def fetch_trending(self, max_count: int = 50) -> List[Dict]:
        """获取微博热搜"""
        # 免费接口：微博热搜榜
        url = "https://weibo.com/ajax/side/hotSearch"
        resp = self.http_client.get(url)
        data = resp.json()
        
        trending = []
        for item in data.get("data", {}).get("realtime", []):
            trending.append({
                "rank": item.get("rank", 0),
                "word": item.get("word", ""),
                "hot_value": item.get("num", 0),
                "label": item.get("label_name", ""),
            })
        
        return trending[:max_count]
```

**数据字段**：

| 字段 | 说明 | 可用性 |
|------|------|--------|
| 正文 text | 微博完整文本 | ✅ |
| 发布时间 | created_at | ✅ |
| 转发数 | reposts_count | ✅ |
| 评论数 | comments_count | ✅ |
| 点赞数 | attitudes_count | ✅ |
| 用户信息 | screen_name, followers_count | ✅ |
| 阅读数 | 官方不开放 | ❌ |

**频率限制**：每分钟不超过 10 次请求，每次间隔 2-3 秒

---

### 3.2 微信公众号（wechat.py）

**数据来源**：RSSHub + 直接抓取

**依赖**：
- `feedparser`（RSS 解析）
- 可选：`rsshub` 自建服务或公共 RSSHub 实例

**实现思路**：

```python
class WeChatCollector(BaseCollector):
    """微信公众号采集器"""
    
    # 方式1：RSSHub（需要部署 RSSHub 服务）
    RSSHUB_URL = "http://localhost:1200"
    
    def fetch_via_rsshub(self, wxid: str) -> List[Dict]:
        """通过 RSSHub 获取公众号文章"""
        url = f"{self.RSSHUB_URL}/wemp/{wxid}"
        resp = self.http_client.get(url)
        feed = feedparser.parse(resp.text)
        
        articles = []
        for entry in feed.entries:
            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": self._clean_html(entry.get("summary", "")),
                "publish_at": entry.get("published", ""),
                "author": entry.get("author", ""),
            })
        
        return articles
    
    # 方式2：直接抓取（通过搜索引擎找到文章列表页）
    def fetch_via_search(self, wxid: str) -> List[Dict]:
        """通过搜索接口获取公众号文章"""
        # 使用搜狗搜索 API（相对稳定）
        url = f"https://weixin.sogou.com/weixin"
        params = {
            "type": 1,
            "s_from": "input",
            "query": wxid,
            "_sug_": "n",
            "_sug_": ""
        }
        # 需要验证码，非最佳方案
        pass
```

**数据字段**：

| 字段 | 说明 | 可用性 |
|------|------|--------|
| 标题 | title | ✅ |
| 链接 | url | ✅ |
| 摘要 | summary | ✅ |
| 发布时间 | publish_at | ✅ |
| 作者 | author | ✅ |
| 正文内容 | 需二次抓取 | ✅ |
| 阅读量/点赞 | 需微信授权 | ❌ |

**推荐方案**：自建 RSSHub（`cooderl/wewe-rss`），更稳定

---

### 3.3 小红书（xiaohongshu.py）

**数据来源**：小红书网页版 API

**实现思路**：

```python
class XiaoHongShuCollector(BaseCollector):
    """小红书采集器"""
    
    # 小红书 API（需 Cookie）
    API_BASE = "https://edith.xiaohongshu.com/api/sns/web/v1"
    
    def fetch_user_notes(self, user_id: str, cookie: str) -> List[Dict]:
        """获取用户笔记列表"""
        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
            "X-s": self._generate_signature(),  # 需要签名
            "X-t": str(int(time.time() * 1000)),
        }
        
        url = f"{self.API_BASE}/user_posted"
        params = {"user_id": user_id, "cursor": "", "num": 20}
        
        resp = self.http_client.get(url, headers=headers, params=params)
        data = resp.json()
        
        notes = []
        for note in data.get("data", {}).get("notes", []):
            notes.append({
                "note_id": note.get("note_id", ""),
                "title": note.get("title", ""),
                "type": note.get("type", ""),  # video/normal
                "liked_count": note.get("interact_info", {}).get("liked_count", 0),
                "collected_count": note.get("interact_info", {}).get("collected_count", 0),
                "comment_count": note.get("interact_info", {}).get("comment_count", 0),
                "share_count": note.get("interact_info", {}).get("share_count", 0),
                "publish_time": note.get("time", 0),
                "cover_url": note.get("cover", {}).get("url_default", ""),
            })
        
        return notes
    
    def fetch_note_detail(self, note_id: str, cookie: str) -> Dict:
        """获取笔记详情（包含正文和评论）"""
        headers = {
            "Cookie": cookie,
            "User-Agent": "...",
            "X-s": self._generate_signature(),
            "X-t": str(int(time.time() * 1000)),
        }
        
        url = f"{self.API_BASE}/feed"
        params = {"source_note_id": note_id}
        
        resp = self.http_client.get(url, headers=headers, params=params)
        data = resp.json()
        
        note = data.get("data", {}).get("items", [{}])[0].get("note_card", {})
        
        return {
            "title": note.get("title", ""),
            "desc": note.get("desc", ""),
            "liked_count": note.get("interact_info", {}).get("liked_count", 0),
            "images": [img.get("url_default", "") for img in note.get("image_list", [])],
        }
```

**数据字段**：

| 字段 | 说明 | 可用性 |
|------|------|--------|
| 标题 | title | ✅ |
| 正文 | desc | ✅ |
| 图片 | images | ✅ |
| 点赞数 | liked_count | ✅ |
| 收藏数 | collected_count | ✅ |
| 评论数 | comment_count | ✅ |
| 发布时间 | time | ✅ |
| 用户信息 | user_id, nickname | ✅ |
| IP属地 | 需登录 | ⚠️ 部分 |

**反爬策略**：
- 需要有效的 Cookie
- 需要 X-s 签名（基于设备信息和时间戳）
- 请求间隔 5-10 秒
- 建议使用代理 IP 池

---

### 3.4 抖音（douyin.py）

**数据来源**：抖音热榜 API（官方免费接口）

**实现思路**：

```python
class DouYinCollector(BaseCollector):
    """抖音采集器"""
    
    # 抖音热榜（无需登录）
    HOT_SEARCH_URL = "https://aweme-hl.snssdk.com/aweme/v1/hot/search/list/"
    
    def fetch_trending(self) -> List[Dict]:
        """获取抖音热榜"""
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            "Accept": "application/json",
        }
        
        resp = self.http_client.get(self.HOT_SEARCH_URL, headers=headers)
        data = resp.json()
        
        trending = []
        for item in data.get("data", {}).get("word_list", []):
            trending.append({
                "rank": item.get("rank", 0),
                "word": item.get("word", ""),
                "hot_value": item.get("hot_value", 0),
                "label": item.get("label", ""),
                "event": item.get("event", ""),
                "video_count": item.get("video_count", 0),
                "讨论数": item.get("discuss_count", 0),
            })
        
        return trending
    
    # 搜索接口（需要 Cookie）
    SEARCH_URL = "https://www.iesdouyin.com/api/fans/data/author/item/list/"
    
    def fetch_user_videos(self, sec_uid: str, cookie: str) -> List[Dict]:
        """获取用户视频列表（需登录）"""
        headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0...",
        }
        
        # 分页参数
        params = {
            "sec_uid": sec_uid,
            "count": 18,
            "max_cursor": 0,
        }
        
        resp = self.http_client.get(self.SEARCH_URL, headers=headers, params=params)
        data = resp.json()
        
        videos = []
        for item in data.get("item_list", []):
            videos.append({
                "aweme_id": item.get("aweme_id", ""),
                "desc": item.get("desc", ""),
                "create_time": item.get("create_time", 0),
                "digg_count": item.get("statistics", {}).get("digg_count", 0),
                "comment_count": item.get("statistics", {}).get("comment_count", 0),
                "share_count": item.get("statistics", {}).get("share_count", 0),
                "play_count": item.get("statistics", {}).get("play_count", 0),
            })
        
        return videos
```

**数据字段**：

| 字段 | 说明 | 可用性 |
|------|------|--------|
| 热搜词 | word | ✅ |
| 热力值 | hot_value | ✅ |
| 标签 | label | ✅ |
| 视频数 | video_count | ✅ |
| 用户视频列表 | 需登录 | ⚠️ |

---

### 3.5 B站（bilibili.py）

**数据来源**：B站官方 API + RSSHub

**实现思路**：

```python
class BilibiliCollector(BaseCollector):
    """B站采集器"""
    
    # B站官方 API（无需登录）
    API_BASE = "https://api.bilibili.com"
    
    def fetch_user_videos(self, uid: int) -> List[Dict]:
        """获取 UP 主视频列表"""
        url = f"{self.API_BASE}/ajax/smdvd/homeData"
        params = {"mid": uid, "page": 1, "pagesize": 30}
        
        resp = self.http_client.get(url, params=params)
        data = resp.json()
        
        videos = []
        for item in data.get("data", {}).get("archives", []):
            videos.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "desc": item.get("desc", ""),
                "pic": item.get("pic", ""),
                "duration": item.get("duration", 0),
                "view": item.get("stat", {}).get("view", 0),
                "like": item.get("stat", {}).get("like", 0),
                "coin": item.get("stat", {}).get("coin", 0),
                "favorite": item.get("stat", {}).get("favorite", 0),
                "reply": item.get("stat", {}).get("reply", 0),
                "publish_time": item.get("pubdate", 0),
            })
        
        return videos
    
    def fetch_trending(self, rid: int = 0) -> List[Dict]:
        """获取排行榜"""
        # rid: 0=全站, 1=动画, 3=音乐...
        url = f"{self.API_BASE}/x/web-interface/ranking/v2"
        params = {"rid": rid}
        
        resp = self.http_client.get(url, params=params)
        data = resp.json()
        
        ranking = []
        for item in data.get("data", {}).get("list", []):
            ranking.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "owner": item.get("owner", {}).get("name", ""),
                "view": item.get("stat", {}).get("view", 0),
                "like": item.get("stat", {}).get("like", 0),
                "reply": item.get("stat", {}).get("reply", 0),
            })
        
        return ranking
    
    def fetch_danmaku(self, aid: int) -> List[Dict]:
        """获取弹幕（最热弹幕）"""
        url = f"{self.API_BASE}/x/v2/reply/main"
        params = {"type": 1, "oid": aid, "mode": 3, "ps": 10}
        
        resp = self.http_client.get(url, params=params)
        data = resp.json()
        
        danmaku = []
        for reply in data.get("data", {}).get("replies", []):
            danmaku.append({
                "uname": reply.get("member", {}).get("uname", ""),
                "content": reply.get("content", {}).get("message", ""),
                "like": reply.get("like", 0),
                "ctime": reply.get("ctime", 0),
            })
        
        return danmaku
```

**数据字段**：

| 字段 | 说明 | 可用性 |
|------|------|--------|
| 标题/描述 | title, desc | ✅ |
| 播放量 | view | ✅ |
| 点赞数 | like | ✅ |
| 硬币数 | coin | ✅ |
| 收藏数 | favorite | ✅ |
| 评论数 | reply | ✅ |
| 弹幕 | 需二次请求 | ✅ |
| UP主信息 | owner | ✅ |

---

### 3.6 知乎（zhihu.py）

**数据来源**：知乎搜索 API

**实现思路**：

```python
class ZhihuCollector(BaseCollector):
    """知乎采集器"""
    
    API_BASE = "https://www.zhihu.com/api/v4"
    
    def fetch_trending(self) -> List[Dict]:
        """获取知乎热榜"""
        url = f"{self.API_BASE}/creators/rank/hot?domain=0"
        headers = {
            "User-Agent": "Mozilla/5.0...",
            "X-API-VERSION": "3.0.40",
        }
        
        resp = self.http_client.get(url, headers=headers)
        data = resp.json()
        
        trending = []
        for item in data.get("data", []):
            trending.append({
                "type": item.get("target", {}).get("type", ""),
                "title": item.get("target", {}).get("title", ""),
                "excerpt": item.get("excerpt", ""),
                "answer_count": item.get("target", {}).get("answer_count", 0),
                "follower_count": item.get("target", {}).get("follower_count", 0),
                "url": item.get("target", {}).get("url", ""),
            })
        
        return trending
    
    def fetch_question_answers(self, question_id: str, max_count: int = 10) -> List[Dict]:
        """获取问题的高赞回答"""
        url = f"{self.API_BASE}/questions/{question_id}/answers"
        params = {
            "sort_by": "voteup",  # 按点赞排序
            "limit": 20,
            "offset": 0,
        }
        headers = {
            "User-Agent": "Mozilla/5.0...",
            "Cookie": self.cookie,  # 需要登录 Cookie
        }
        
        resp = self.http_client.get(url, headers=headers, params=params)
        data = resp.json()
        
        answers = []
        for item in data.get("data", [])[:max_count]:
            answers.append({
                "answer_id": item.get("id", ""),
                "author": item.get("author", {}).get("name", ""),
                "voteup_count": item.get("voteup_count", 0),
                "content": item.get("content", ""),  # HTML 格式
                "created_time": item.get("created_time", 0),
            })
        
        return answers
```

---

## 四、CLI 命令设计

### 4.1 主入口

```python
# cli.py
import click
from .platforms.weibo import WeiboCollector
from .platforms.wechat import WeChatCollector
from .platforms.xiaohongshu import XiaoHongShuCollector
from .platforms.douyin import DouYinCollector
from .platforms.bilibili import BilibiliCollector
from .platforms.zhihu import ZhihuCollector

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """社交媒体监控 CLI

    支持平台：微博、微信公众号、小红书、抖音、B站、知乎

    示例：
        social-monitor fetch weibo --uid 1974576991
        social-monitor fetch douyin trending
        social-monitor fetch bilibili --uid 614946423
    """
    pass
```

### 4.2 fetch 子命令

```python
@cli.group()
def fetch():
    """采集指定平台数据"""
    pass

@fetch.command("weibo")
@click.option("--uid", required=True, help="微博 UID")
@click.option("--pages", default=5, help="抓取页数")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "csv", "print"]))
@click.option("--cookie", help="微博 Cookie（可选，提升数据完整度）")
def fetch_weibo(uid, pages, output, cookie):
    """采集微博用户动态"""
    collector = WeiboCollector(cookie=cookie)
    data = collector.fetch_user_timeline(uid, max_page=pages)
    _output(data, output)

@fetch.command("weibo-trending")
@click.option("--count", default=50, help="热搜条数")
@click.option("--output", "-o", default="json")
def fetch_weibo_trending(count, output):
    """采集微博热搜榜"""
    collector = WeiboCollector()
    data = collector.fetch_trending(max_count=count)
    _output(data, output)

@fetch.command("wechat")
@click.option("--wxid", required=True, help="微信公众号 ID")
@click.option("--output", "-o", default="json")
@click.option("--rsshub-url", default="http://localhost:1200", help="RSSHub 地址")
def fetch_wechat(wxid, output, rsshub_url):
    """采集微信公众号文章"""
    collector = WeChatCollector(rsshub_url=rsshub_url)
    data = collector.fetch_via_rsshub(wxid)
    _output(data, output)

@fetch.command("xiaohongshu")
@click.option("--user-id", required=True, help="小红书用户 ID")
@click.option("--cookie", required=True, help="小红书 Cookie")
@click.option("--output", "-o", default="json")
def fetch_xiaohongshu(user_id, cookie, output):
    """采集小红书用户笔记"""
    collector = XiaoHongShuCollector(cookie=cookie)
    data = collector.fetch_user_notes(user_id)
    _output(data, output)

@fetch.command("douyin-trending")
@click.option("--count", default=50, help="热榜条数")
@click.option("--output", "-o", default="json")
def fetch_douyin_trending(count, output):
    """采集抖音热榜"""
    collector = DouYinCollector()
    data = collector.fetch_trending()
    _output(data[:count], output)

@fetch.command("bilibili")
@click.option("--uid", required=True, help="B站 UP 主 UID")
@click.option("--output", "-o", default="json")
@click.option("--type", default="video", type=click.Choice(["video", "ranking"]))
def fetch_bilibili(uid, output, type):
    """采集B站 UP主视频"""
    collector = BilibiliCollector()
    if type == "video":
        data = collector.fetch_user_videos(uid)
    else:
        data = collector.fetch_trending()
    _output(data, output)

@fetch.command("zhihu-trending")
@click.option("--count", default=20, help="热榜条数")
@click.option("--output", "-o", default="json")
def fetch_zhihu_trending(count, output):
    """采集知乎热榜"""
    collector = ZhihuCollector()
    data = collector.fetch_trending()
    _output(data[:count], output)
```

### 4.3 notify 子命令

```python
@cli.group()
def notify():
    """通知相关命令"""
    pass

@notify.command("feishu")
@click.option("--webhook", required=True, help="飞书 Webhook URL")
@click.option("--data", required=True, help="JSON 数据文件路径")
@click.option("--platform", required=True, help="平台名称")
@click.option("--title", default="社交媒体监控", help="通知标题")
def notify_feishu(webhook, data, platform, title):
    """发送飞书通知"""
    with open(data, "r") as f:
        items = json.load(f)

    notifier = FeishuNotifier(webhook_url=webhook)
    notifier.notify_new_content(platform, len(items), items[:5])
    click.echo(f"已发送 {platform} 通知，共 {len(items)} 条")
```

### 4.4 config 子命令

```python
@cli.group()
def config():
    """配置管理"""
    pass

@config.command("init")
def config_init():
    """初始化配置文件"""
    config_dir = Path.home() / ".social-monitor"
    config_dir.mkdir(exist_ok=True)

    default_config = {
        "weibo": {"cookie": ""},
        "xiaohongshu": {"cookie": ""},
        "rsshub_url": "http://localhost:1200",
        "feishu_webhook": "",
    }

    config_file = config_dir / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(default_config, f)

    click.echo(f"配置文件已创建: {config_file}")

@config.command("show")
def config_show():
    """显示当前配置"""
    config_file = Path.home() / ".social-monitor" / "config.yaml"
    if not config_file.exists():
        click.echo("配置文件不存在，请先运行 config init")
        return

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    click.echo(yaml.dump(config, default_flow_style=False))
```

---

## 五、存储层设计

默认使用本地 **PostgreSQL** 存储；仍支持 JSON 文件与 MySQL（可选）。

### 5.1 PostgreSQL 存储（默认）

```python
# storage/postgres_storage.py
import json
import psycopg2

class PostgresStorage:
    """PostgreSQL 存储"""

    def __init__(self, config: dict):
        self.connection = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("user", "postgres"),
            password=config.get("password", ""),
            dbname=config.get("database", "social_monitor"),
        )
        self.create_table()

    def save(self, platform, account_id, items, mode="append"):
        if mode == "replace":
            # 全量替换：先删后插
            ...
        # ON CONFLICT (platform, account_id, content_id) DO UPDATE
        ...

    def load(self, platform, account_id) -> List[Dict]:
        # SELECT raw_data FROM sm_content WHERE ...
        ...
```

本地数据库可通过 `docker compose up -d` 启动（见项目根目录 `docker-compose.yml`）。

配置示例（`~/.social-monitor/config.yaml`）：

```yaml
storage:
  type: postgres

postgres:
  host: localhost
  port: 5432
  user: postgres
  password: postgres
  database: social_monitor
```

### 5.2 JSON 文件存储（可选）

```python
# storage/json_storage.py
import json
from pathlib import Path
from datetime import datetime

class JSONStorage:
    """JSON 文件存储"""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or Path.home() / ".social-monitor" / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, platform: str, account_id: str, items: List[Dict], mode: str = "append"):
        """保存数据到 JSON 文件

        Args:
            platform: 平台名称
            account_id: 账号 ID
            items: 数据列表
            mode: append(追加) / replace(替换)
        """
        filepath = self.data_dir / f"{platform}_{account_id}.json"

        if mode == "append" and filepath.exists():
            with open(filepath, "r") as f:
                existing = json.load(f)
            existing_ids = {item.get("id") for item in existing}
            for item in items:
                if item.get("id") not in existing_ids:
                    existing.append(item)
            items = existing

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        return len(items)

    def load(self, platform: str, account_id: str) -> List[Dict]:
        """加载数据"""
        filepath = self.data_dir / f"{platform}_{account_id}.json"
        if not filepath.exists():
            return []

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
```

### 5.3 MySQL 存储（可选）

```python
# storage/mysql_storage.py
import pymysql
from typing import List, Dict

class MySQLStorage:
    """MySQL 存储"""

    def __init__(self, config: dict):
        self.connection = pymysql.connect(
            host=config["host"],
            port=config.get("port", 3306),
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset="utf8mb4",
        )

    def save(self, platform: str, account_id: str, items: List[Dict]):
        """保存到 MySQL"""
        with self.connection.cursor() as cursor:
            for item in items:
                cursor.execute("""
                    INSERT INTO sm_content
                    (platform, account_id, content_id, title, content_text,
                     publish_at, likes_count, comments_count, reposts_count,
                     raw_data, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    likes_count = VALUES(likes_count),
                    comments_count = VALUES(comments_count),
                    reposts_count = VALUES(reposts_count)
                """, (
                    platform, account_id,
                    item.get("id", ""),
                    item.get("title", ""),
                    item.get("text", ""),
                    item.get("publish_at", ""),
                    item.get("likes", 0),
                    item.get("comments", 0),
                    item.get("reposts", 0),
                    json.dumps(item, ensure_ascii=False),
                ))
        self.connection.commit()

    def create_table(self):
        """创建表结构"""
        with self.connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sm_content (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    account_id VARCHAR(100) NOT NULL,
                    content_id VARCHAR(100),
                    title VARCHAR(500),
                    content_text TEXT,
                    publish_at DATETIME,
                    likes_count INT DEFAULT 0,
                    comments_count INT DEFAULT 0,
                    reposts_count INT DEFAULT 0,
                    raw_data JSON,
                    created_at DATETIME DEFAULT NOW(),
                    INDEX idx_platform_account (platform, account_id),
                    INDEX idx_publish_at (publish_at),
                    UNIQUE KEY uk_content (platform, account_id, content_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        self.connection.commit()
```

---

## 六、通知层设计

### 6.1 飞书通知

```python
# notifiers/feishu.py
import httpx
from typing import List, Dict

class FeishuNotifier:
    """飞书通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, msg_type: str, content: dict):
        """发送消息"""
        payload = {"msg_type": msg_type, content: content}
        resp = httpx.post(self.webhook_url, json=payload, timeout=10)
        return resp.json()

    def notify_new_content(self, platform: str, account_name: str, items: List[Dict]):
        """通知新内容"""
        if not items:
            return

        content = f"📢 **{account_name}** ({platform}) 新增 {len(items)} 条动态\n\n"
        for item in items[:5]:
            title = item.get("title", item.get("text", ""))[:50]
            content += f"• {title}...\n"

        self.send("text", {"text": content})

    def notify_trending(self, platform: str, items: List[Dict]):
        """通知热榜更新"""
        if not items:
            return

        content = f"🔥 **{platform}** 热榜 TOP {len(items)}\n\n"
        for i, item in enumerate(items[:10], 1):
            word = item.get("word", item.get("title", ""))
            hot_value = item.get("hot_value", item.get("view", 0))
            content += f"{i}. {word} ({hot_value:,})\n"

        self.send("text", {"text": content})
```

---

## 七、OpenClaw 集成

### 7.1 Skill 封装

```yaml
# social-monitor/SKILL.md
name: social-monitor
description: 社交媒体监控 CLI，支持微博/微信/小红书/抖音/B站/知乎数据采集
version: 1.0.0

commands:
  - name: fetch-weibo
    description: 采集微博用户动态
    command: social-monitor fetch weibo --uid {uid} --pages {pages}

  - name: fetch-weibo-trending
    description: 采集微博热搜榜
    command: social-monitor fetch weibo-trending --count {count}

  - name: fetch-douyin-trending
    description: 采集抖音热榜
    command: social-monitor fetch douyin-trending --count {count}

  - name: fetch-bilibili
    description: 采集B站UP主视频
    command: social-monitor fetch bilibili --uid {uid}

  - name: fetch-wechat
    description: 采集微信公众号文章
    command: social-monitor fetch wechat --wxid {wxid}

  - name: notify-feishu
    description: 发送飞书通知
    command: social-monitor notify feishu --webhook {webhook} --data {data} --platform {platform}
```

### 7.2 OpenClaw 调用示例

```python
# 方式1：exec 直接调用
exec(command="social-monitor fetch weibo --uid 1974576991 --pages 10 --output json")

# 方式2：sessions_spawn 后台采集
sessions_spawn(
    task="social-monitor fetch weibo --uid 1974576991 --pages 10 --output json",
    taskName="weibo-fetch-比亚迪官方"
)

# 方式3：Cron 定时任务
# 每天9点采集微博热搜
npx openclaw cron add \
  --name "微博热搜-每日" \
  --command "social-monitor fetch weibo-trending --count 50" \
  --schedule "0 9 * * *"
```

---

## 八、实施计划

### Phase 1：项目骨架 + 简单平台（1天）

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 项目脚手架创建 | 1h | 目录结构、requirements.txt |
| 微博 CLI 实现 | 2h | weibo.py + 命令 |
| 抖音热榜 CLI 实现 | 1h | douyin.py + 命令 |
| B站 CLI 实现 | 1h | bilibili.py + 命令 |

### Phase 2：中等复杂度平台（1天）

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 微信公众号 CLI | 2h | wechat.py + RSSHub 集成 |
| 知乎 CLI | 1h | zhihu.py + 命令 |
| PostgreSQL 存储层 | 1h | postgres_storage.py |
| JSON 存储层（可选） | 1h | json_storage.py |

### Phase 3：小红书 + 完善（1天）

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 小红书 CLI | 3h | xiaohongshu.py（含签名逻辑） |
| 飞书通知 | 1h | feishu.py |
| MySQL 存储 | 1h | mysql_storage.py |

### Phase 4：OpenClaw 集成（1天）

| 任务 | 工时 | 交付物 |
|------|------|--------|
| Skill 封装 | 2h | SKILL.md |
| Cron 任务配置 | 2h | 定时任务配置 |

---

**总工时：约 5 人天**

---

## 九、依赖清单

```
# requirements.txt
click>=8.0.0
httpx>=0.24.0
feedparser>=6.0.0
PyYAML>=6.0
psycopg2-binary>=2.9.0  # PostgreSQL 默认存储
pymysql>=1.0.0          # 可选 MySQL

# 可选：增强功能
# playwright>=1.30.0  # 复杂页面备用方案
# scrapy>=2.6.0       # 大规模爬虫
```

---

## 十、总结

social-monitor CLI 是轻量级社交媒体监控工具，与 Octopus CLI 形成互补：

- **Octopus**：复杂页面、模板化、云端、企业级
- **social-monitor**：轻量快速、API直连、高频轮询、开源零成本

两者结合，形成完整的社交媒体监控采集能力。

---

*版本：v1.0 | 编制日期：2026-06-16*
