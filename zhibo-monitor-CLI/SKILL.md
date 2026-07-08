---
name: zhibo-monitor
description: 新能源车企发布会直播监控与分析 CLI
version: 0.1.0
metadata:
  cli_command: zhibo-monitor
  requires_install: true
  agent_safe_commands:
    - init-db
    - start-demo
  human_required_commands:
    - login
---

# zhibo-monitor

## 前置条件

```bash
pip install -e .
zhibo-monitor --version
```

## Agent 推荐命令

初始化数据库：

```bash
zhibo-monitor init-db
```

演示模式（不启动浏览器）：

```bash
zhibo-monitor start bilibili 22603245 --demo
```

## 长任务说明

`start` 为阻塞式直播监控，须后台运行（cron / nohup），禁止 Agent 同步等待。

## 禁止 Agent 自动调用

| 命令 | 原因 |
|------|------|
| `login` | 需人工扫码 |
| `start`（无 --demo） | 长任务阻塞 |
