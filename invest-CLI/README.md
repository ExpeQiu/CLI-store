# invest CLI

投资决策系统命令行工具 — 宏观评分、三维共振信号、模拟交易。

## 安装

```bash
cd invest-CLI
pip install -e .
invest --version
```

可选数据源依赖：

```bash
pip install -e ".[data]"
```

## 快速开始

```bash
invest account status --demo          # 账户 + 市场评分（离线）
invest market score --demo --format json
invest market macro --demo
invest signal list --demo
invest trade buy 600519 100 --dry-run  # 预览，不写入
```

## 配置

| 路径 | 说明 |
|------|------|
| `~/.invest/config.yaml` | 用户配置 |
| `~/.invest/invest_state.json` | 模拟账户状态 |
| `.env` | 密钥（见 `.env.example`） |

优先级：CLI 参数 > 环境变量 > 配置文件 > 默认值

```bash
cp .env.example .env
cp config.yaml.example ~/.invest/config.yaml
```

## 命令

| 命令 | 说明 |
|------|------|
| `invest account status` | 账户概览 + 市场评分 |
| `invest market macro` | 宏观数据 |
| `invest market score` | 三维共振评分 |
| `invest signal list` | 决策信号 |
| `invest trade buy/sell` | 模拟交易 |

全局选项：`--help` `--version` `-v` `-q`  
输出选项：`--format json|table` `-o` `--demo`

## 退出码

| Code | 含义 |
|------|------|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 无数据 |
| 3 | 采集失败 |

## Agent 接入

见 [SKILL.md](SKILL.md) 与 [agent/manifest.json](agent/manifest.json)。

## 开发与验证

```bash
./verify.sh
```

设计文档见 [guide/architecture.md](guide/architecture.md)。
