# github-trend

GitHub 热门仓库趋势采集 CLI。

## 安装

```bash
pip install -e .
github-trend --version
```

## 快速开始

```bash
github-trend fetch trending --demo --format json
github-trend fetch trending --since weekly --format table

# 同步高星项目到飞书 Bitable
github-trend bitable sync --demo --dry-run
```

## 配置

复制 `.env.example` 为 `.env`，设置：

| 变量 | 说明 |
|------|------|
| `GITHUB_TOKEN` | GitHub API Token（可选，提高限额） |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_APP_TOKEN` | 飞书 Bitable App Token（可选） |
| `FEISHU_TABLE_ID` | 飞书 Bitable Table ID（可选） |

## 验证

```bash
./verify.sh
```

## Agent 接入

见 [SKILL.md](SKILL.md) 与 [agent/manifest.json](agent/manifest.json)。
