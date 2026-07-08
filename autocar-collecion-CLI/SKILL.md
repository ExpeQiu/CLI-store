---
name: clauto
description: 汽车行业 CLI 自动化工具（工信部公告 / 汽车新闻 / 车型监测）
version: 0.2.0
metadata:
  cli_command: clauto
  requires_install: true
  agent_safe_commands:
    - miit-demo
    - news-demo
    - monitor-demo
  human_required_commands: []
---

# clauto

## 前置条件

```bash
pip install -e .
clauto --version
```

## Agent 推荐命令

工信部公告（离线 demo）：

```bash
clauto miit --demo --format json
```

- 退出码：0 成功 / 2 无数据 / 3 采集失败
- JSON 字段：`module`, `data_source`, `fetched_at`, `announcements`

车型监测 demo：

```bash
clauto monitor -b 比亚迪 -m 海豹 --demo --format json
```

## 输出解析

- stdout = 数据
- stderr = 日志
