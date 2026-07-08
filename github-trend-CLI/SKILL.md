---
name: github-trend
description: GitHub 热门仓库趋势采集 CLI，支持 Trending 榜单抓取与飞书 Bitable 同步
version: 0.2.0
metadata:
  cli_command: github-trend
  requires_install: true
  agent_safe_commands:
    - fetch-trending-demo
    - fetch-trending
    - bitable-sync-demo
---

# github-trend

## Agent 推荐命令

采集 GitHub Trending（演示）：

```bash
github-trend fetch trending --demo --format json
```

- 退出码：0 成功 / 2 无数据 / 3 采集失败
- 输出字段：`items[].rank`, `items[].repo`, `items[].description`, `items[].language`, `items[].stars_today`, `items[].url`

采集 GitHub Trending（实时）：

```bash
github-trend fetch trending --since weekly --format json
```

- 参数：`--since` daily | weekly | monthly

同步 GitHub 高星项目到飞书 Bitable（演示）：

```bash
github-trend bitable sync --demo --format json
```

同步到飞书 Bitable（实时）：

```bash
github-trend bitable sync --dry-run --format json
```

- 需要环境变量：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`
- `--dry-run` 只预览不写入

## 禁止 Agent 调用

| 命令 | 原因 |
|------|------|
| - | 当前所有命令均为只读或预览，无危险操作 |

## 输出格式

默认 `--format json` 输出包含元数据：

```json
{
  "module": "github-trending",
  "data_source": "live|demo",
  "fetched_at": "2026-06-25T10:00:00+08:00",
  "count": 20,
  "items": [...]
}
```
