---
name: invest
description: 投资决策系统 CLI — 宏观评分、三维共振信号、模拟交易
version: 2.3.0
metadata:
  cli_command: invest
  requires_install: true
  agent_safe_commands:
    - market-score-demo
    - market-macro-demo
    - account-status-demo
    - signal-list-demo
  human_required_commands:
    - trade-buy
    - trade-sell
---

# invest

## 前置条件

```bash
cd invest-CLI && pip install -e .
invest --version
```

## Agent 推荐命令

市场评分（演示，agent_safe: true）：

```bash
invest market score --demo --format json
```

- 退出码：0 成功 / 2 无数据 / 3 采集失败
- 输出字段：`total`, `grade`, `recommendation`, `components[]`

账户状态（演示）：

```bash
invest account status --demo --format json
```

宏观数据（演示）：

```bash
invest market macro --demo --format json
```

决策信号（演示）：

```bash
invest signal list --demo --format json
```

## 禁止 Agent 自动调用

| 命令 | 原因 |
|------|------|
| `invest trade buy` | 写入本地 state，需用户确认 |
| `invest trade sell` | 写入本地 state，需用户确认 |

可使用 `--dry-run` 预览买卖操作。

## 输出格式

数据走 stdout（JSON），日志走 stderr。

```json
{
  "module": "market-score",
  "version": "2.3.0",
  "data_source": "demo|live",
  "fetched_at": "2026-06-26T10:00:00+08:00"
}
```
