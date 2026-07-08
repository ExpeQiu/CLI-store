# 15CLI

Compo 生态下的命令行工具集合，涵盖社媒监控、直播采集、汽车情报等场景。

## 标准

新建或重构 CLI 子项目前，请先阅读 **[CLI标准.md](./CLI标准.md)**，其中 **§15 Agent 平台接入规范** 定义了 OpenClaw / Hermes 等平台的 SKILL 与 manifest 要求。

## 子项目

| 项目 | 命令 | 说明 |
|------|------|------|
| [social-monitor-CLI](./social-monitor-CLI/) | `social-monitor` | 微博/微信/小红书/抖音/B站/知乎采集 |
| [autocar-collecion-CLI](./autocar-collecion-CLI/) | `clauto` | 工信部公告 / 汽车新闻 / 车型监测 |
| [zhibo-monitor-CLI](./zhibo-monitor-CLI/) | `zhibo-monitor`* | 新能源发布会直播监控 |
| github-trend-CLI | — | 规划中 |
| intelligence-collection-CLI | — | 规划中 |

\* zhibo-monitor 当前为 `main.py` 入口，待按标准迁移为 `console_scripts`。

## 快速验证

```bash
cd social-monitor-CLI && ./verify.sh
cd autocar-collecion-CLI && ./verify.sh
```
