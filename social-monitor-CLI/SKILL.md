---
name: social-monitor
description: 社交媒体监控 CLI，支持微博/微信/小红书/抖音/B站/知乎数据采集
version: 1.0.0
metadata:
  cli_command: social-monitor
  requires_install: true
  agent_safe_commands:
    - fetch-weibo-trending
    - fetch-douyin-trending
    - fetch-zhihu-trending
    - intel-trending
  human_required_commands:
    - config-login-xiaohongshu
---

# social-monitor

## 前置条件

```bash
pip install -e .
social-monitor --version
```

Cookie 可选配置见 `config.yaml.example` 或 `.env.example`。

## Agent 推荐命令

采集微博热搜（agent_safe: true）：

```bash
social-monitor fetch weibo-trending --count 20 --format json
```

离线验收：

```bash
social-monitor fetch weibo-trending --count 5 --format json --demo
```

- 参数：`--count` 条数（默认 50）；`--format json|csv|print|table`
- 退出码：0 成功 / 2 无数据 / 3 采集失败
- 输出字段：`items[].word`, `items[].hot_value`, `data_source`, `fetched_at`

批量热榜增量：

```bash
social-monitor intel trending --diff --format json
```

## 长任务说明

`monitor run --task live` 为阻塞式长任务，须通过 cron / nohup / spawn 后台运行，禁止 Agent 同步等待。

## 禁止 Agent 自动调用

| 命令 | 原因 |
|------|------|
| `config login *` | 需人工扫码 |
| `config cookie set` | 涉及凭证写入 |

## 输出解析

- stdout = 数据（JSON 等）
- stderr = 日志与进度
