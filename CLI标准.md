# 15CLI 通用 CLI 构建标准

> v1.0.0 · 基于 `15CLI` 现有子项目实践，对齐 [CLI Guidelines](https://clig.dev/)、[12 Factor CLI Apps](https://12factor.net/) 与 Compo 可观测约定。

## 1. 适用范围

本标准适用于 `15CLI` 目录下所有命令行工具，以及 Compo 生态中「数据采集 / 监控 / 自动化调度」类 CLI 子项目。

| 现有项目 | CLI 命令 | 成熟度 | 可参照点 |
|---------|---------|--------|---------|
| social-monitor-CLI | `social-monitor` | ★★★ | 分包结构、Click 命令组、verify、Mock 测试 |
| autocar-collecion-CLI | `clauto` | ★★★ | exit code 分层、JSON 契约、`--demo` |
| zhibo-monitor-CLI | `python main.py` | ★★☆ | Typer、长任务、Alembic 迁移 |
| github-trend-CLI | — | 待建 | — |
| intelligence-collection-CLI | — | 待建 | — |

---

## 2. 设计原则

1. **Unix 哲学**：做好一件事；可组合（stdout 管道）；可脚本化（稳定 exit code）。
2. **人机双友好**：人类可读默认输出；机器可读 `--format json`；日志走 stderr，数据走 stdout。
3. **可离线验证**：必须提供 `--demo` / Mock 路径，使 `verify.sh` 不依赖外网也能通过核心链路。
4. **配置外置**：密钥、Cookie、DB 连接不进代码；优先级：**CLI 参数 > 环境变量 > 本地文件 > 默认配置**。
5. **小步可验收**：每个子命令可独立运行；`verify.sh` 覆盖 help、demo、契约 smoke。

---

## 3. 命名规范

### 3.1 仓库 / 目录

```
{domain}-{purpose}-CLI/
```

- 全小写，单词用 `-` 连接，后缀固定 `-CLI`
- 示例：`social-monitor-CLI`、`zhibo-monitor-CLI`

### 3.2 可执行命令名

- 全小写 kebab-case，2～3 个词为宜
- 通过 `pyproject.toml` / `setup.py` 的 `console_scripts` 注册，**禁止**要求用户 `python main.py`
- 示例：`social-monitor`、`clauto`、`zhibo-monitor`

### 3.3 命令与子命令

采用 **`<tool> <group> <action>`** 三层结构（group 可省略）：

```bash
social-monitor fetch weibo-trending --count 20
social-monitor config init
clauto miit --demo
zhibo-monitor login sph
zhibo-monitor start bilibili 22603245
```

| 层级 | 命名 | 示例 |
|------|------|------|
| 顶层 group | 名词：业务域 | `fetch` `config` `monitor` `intel` |
| 子 action | 动词或平台名 | `weibo-trending` `init` `run` |
| 全局 flag | 通用语义 | `--format` `--output` `--demo` `--verbose` |

**禁止**：同一语义多种写法（如同时支持 `get` 与 `fetch` 且无 alias 说明）。

---

## 4. 目录结构（标准模板）

```
{project}-CLI/
├── pyproject.toml          # 推荐：打包、依赖、entry_points
├── README.md               # 安装、快速开始、配置说明
├── verify.sh               # 一键验收（必须）
├── .env.example            # 环境变量模板（不含真实密钥）
├── config.yaml.example     # 可选：业务配置模板
├── guide/                  # 设计文档、实战清单、反爬研究等
├── scripts/                # 辅助脚本（backfill、迁移、编排）
│   ├── start.sh            # 可选：守护/定时任务启动
│   └── stop.sh             # 可选：对应停止
├── tests/                  # pytest 单元 / 集成测试
├── {package_name}/         # Python 包（与 CLI 命令名对应或简写）
│   ├── __init__.py
│   ├── __version__.py
│   ├── cli.py              # 唯一 CLI 入口（Click / Typer）
│   ├── config.py           # 配置加载
│   ├── platforms/          # 或 scraper/、collectors/
│   │   └── base.py         # 采集器抽象基类
│   └── utils/
│       ├── logger.py
│       └── errors.py
├── SKILL.md                # Agent Skills 标准（Hermes / OpenClaw）
└── agent/
    └── manifest.json       # 机器可读：命令 Schema、agent_safe 标记
```

**过渡期允许**：根目录 `main.py` + Typer（如 zhibo-monitor），但新项目应直接采用包结构 + `console_scripts`。

---

## 5. 技术选型

| 项 | 标准 | 说明 |
|----|------|------|
| 语言 | Python ≥ 3.9 | 与现有子项目一致 |
| CLI 框架 | **Click**（首选）或 **Typer** | 复杂命令组用 Click；快速原型可用 Typer |
| 打包 | `pyproject.toml` + setuptools | 新项目禁止仅用裸 `requirements.txt` |
| HTTP | httpx（异步场景 aiohttp） | 统一超时、重试封装 |
| 配置 | PyYAML + pydantic-settings（可选） | 类型校验、.env 加载 |
| 浏览器采集 | playwright（extras） | 独立 optional 依赖组 |
| DB | SQLAlchemy + Alembic（有持久化时） | 迁移脚本放 `migrations/` |

---

## 6. 命令接口规范

### 6.1 全局选项（每个 CLI 必须支持）

| 选项 | 说明 |
|------|------|
| `--help` | 命令 / 子命令帮助 |
| `--version` | 显示 `{prog} {version}` |
| `-v` / `--verbose` | DEBUG 日志 |
| `-q` / `--quiet` | 仅 WARNING 及以上 |

### 6.2 输出选项（数据采集类必须支持）

| 选项 | 说明 |
|------|------|
| `--format` | `table`（默认，人类可读）\| `json` \| `csv` \| `markdown` |
| `-o` / `--output` | 写入文件；未指定则 stdout |
| `--demo` | 使用内置示例数据，不访问外网 |

### 6.3 行为选项

| 选项 | 场景 |
|------|------|
| `--dry-run` | 编排 / 写入 / 通知类命令，只预览不执行 |
| `--force` | 覆盖已有结果（需二次确认或明确文档） |
| `--save` | 持久化到 DB / 本地存储 |
| `--diff` | 与历史快照对比，仅输出增量 |

### 6.4 stdout / stderr 分离

```python
# 数据 → stdout（可被 pipe / jq 消费）
click.echo(json.dumps(data, ensure_ascii=False))

# 进度、统计、警告 → stderr
click.echo(f"已保存 {total} 条", err=True)

# 日志 → stderr（logging StreamHandler(sys.stderr)）
```

---

## 7. 退出码（Exit Code）

统一语义，便于 Shell / CI / Agent 编排：

| Code | 含义 | 典型场景 |
|------|------|---------|
| `0` | 成功 | 有数据或无数据但属预期（如无新热搜） |
| `1` | 通用错误 | 参数错误、配置缺失、未捕获异常 |
| `2` | 无数据 | 抓取成功但结果为空（如无 API Key 时的 news） |
| `3` | 采集失败 | 网络 / 反爬 / 解析失败 |
| `130` | 用户中断 | Ctrl+C（可选，Python 默认） |

```python
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 2
EXIT_SCRAPE_FAIL = 3

def main() -> int:
    ...
    return EXIT_OK

if __name__ == "__main__":
    sys.exit(main())
```

Typer / Click 中：`raise typer.Exit(code=EXIT_NO_DATA)` 或 `raise SystemExit(EXIT_NO_DATA)`。

---

## 8. 配置与密钥

### 8.1 配置文件位置

```
~/.{tool-name}/config.yaml     # 用户级（推荐）
./config.yaml                  # 项目级（开发 / 部署）
.env                           # 密钥（gitignore，提供 .env.example）
```

### 8.2 优先级

```
CLI 参数  >  环境变量  >  cookies/*.txt / auth/*.json  >  config.yaml  >  默认值
```

### 8.3 环境变量命名

```
{TOOL}_{KEY}          # 例：SOCIAL_MONITOR_RSSHUB_URL
{TOOL}_MOCK_MODE      # true 时走 Mock（与 --demo 等价）
```

### 8.4 禁止事项

- 仓库内提交 `.env`、`*_state.json`、真实 Cookie
- 日志中打印完整 Cookie / Token

---

## 9. 日志规范

与 [compo-standards/observability.md](../compo-standards/observability.md) 对齐：

```python
# 格式
"%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# 默认 INFO；--verbose → DEBUG；--quiet → WARNING
# 输出目标：stderr
```

长任务 / 守护进程额外建议：

- 启动时打印：版本、配置摘要（脱敏）、任务 ID
- 关键步骤：`开始抓取` / `写入 N 条` / `任务结束`
- 可选：`request_id` 贯穿一次 fetch 链路

---

## 10. 数据输出契约（JSON）

采集类命令的 `--format json` 应包含元数据字段，便于下游 Agent / Pipeline 解析：

```json
{
  "module": "weibo-trending",
  "version": "1.0.0",
  "data_source": "live",
  "fetched_at": "2026-06-25T10:00:00+08:00",
  "count": 20,
  "items": [ ... ]
}
```

| 字段 | 必须 | 说明 |
|------|------|------|
| `module` | ✓ | 子命令标识 |
| `data_source` | ✓ | `live` \| `demo` \| `cache` |
| `items` / 业务字段 | ✓ | 实际载荷 |
| `fetched_at` | 推荐 | ISO8601 |
| `warnings` | 可选 | 非致命问题列表 |

参考实现：`clauto` 的 `miit --format json` + `verify.sh` 契约校验。

---

## 11. 打包与安装

### 11.1 pyproject.toml 最小模板

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "social-monitor"
version = "1.0.0"
description = "轻量级社交媒体监控命令行工具"
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
    "click>=8.0.0",
    "httpx>=0.24.0",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
postgres = ["psycopg2-binary>=2.9.0"]
browser = ["playwright>=1.30.0"]

[project.scripts]
social-monitor = "social_monitor.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["social_monitor*"]
```

### 11.2 安装方式（README 必须写清）

```bash
pip install -e ".[postgres]"    # 开发
pip install .                   # 生产
{tool} --version                # 验证
```

---

## 12. 生命周期脚本

### 12.1 verify.sh（必须）

根目录提供可执行 `verify.sh`，至少覆盖：

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 1. 安装 / 依赖
pip install -q -e .

# 2. CLI 基础
{tool} --version
{tool} --help

# 3. 离线 smoke（--demo 或 pytest mock）
{tool} {subcmd} --demo

# 4. JSON 契约（可选 python -c 断言）
# 5. 单元测试 pytest -q tests/
# 6. 外网 smoke（失败可 ⚠ 警告，不阻断离线 CI）
```

参考：`social-monitor-CLI/verify.sh`、`autocar-collecion-CLI/verify.sh`。

### 12.2 start.sh / stop.sh（长任务可选）

- 用于 cron、systemd、docker compose 侧车
- 必须成对出现；`stop.sh` 应能按 PID / 锁文件清理
- 日志重定向到 `logs/` 或 journald

---

## 13. 测试规范

| 层级 | 位置 | 要求 |
|------|------|------|
| 单元测试 | `tests/test_*.py` | 解析器、diff、配置加载 |
| Mock 链路 | `tests/` + `--demo` | 不依赖外网即可 CI |
| verify smoke | `verify.sh` | 发布前人工 / CI 一键跑 |
| 外网回归 | 可选 nightly | 标记 `@pytest.mark.network` |

命名：`test_{module}_{behavior}.py`

---

## 14. 文档规范

### 14.1 README.md 必含章节

1. 一句话描述
2. 安装
3. 快速开始（3～5 条最常用命令）
4. 配置（路径、优先级、示例文件）
5. 可选能力（extras：`[browser]` `[postgres]`）
6. 开发与验证：`./verify.sh`

### 14.2 guide/ 建议内容

- 技术设计 / 数据模型
- 平台接入实战清单
- 反爬 / 限流策略备忘

### 14.3 Agent 接入文件（推荐）

每个 CLI 项目应提供 **SKILL.md** + **agent/manifest.json**，详见 [§15 Agent 平台接入规范](#15-agent-平台接入规范)。

---

## 15. Agent 平台接入规范

本节定义 CLI 如何被 **OpenClaw**、**Hermes Agent**、**Task-platform**、**SkillForge（MCP）** 等平台发现与调用。

### 15.1 接入路径总览

| 平台 | 调用方式 | 依赖文件 | 是否「零配置直连」 |
|------|---------|---------|-------------------|
| OpenClaw | `Bash` / `exec` 执行 shell | `SKILL.md` | ✅ 安装 CLI 即可 |
| Hermes Agent | `terminal` 工具 + Skill slash command | `SKILL.md`（Agent Skills 格式） | ✅ 安装 + `hermes skills install` |
| Task-platform | 任务下发 → Agent 自行调 CLI | `SKILL.md` + `manifest.json` | ⚠️ 间接 |
| SkillForge / MCP | `tools/list` → `tools/call` | `manifest.json` + MCP 适配层 | ❌ 需 MCP 包装 |
| Cursor | Agent 读 Skill / 执行终端 | `SKILL.md` | ✅ |

> **注意**：OpenClaw 的 `cliBackends` 用于本地 **LLM CLI 推理后端**（如 claude-cli），不是业务 CLI 接入点。

### 15.2 目录与文件

```
{project}-CLI/
├── SKILL.md                 # 人类 + Agent 可读的操作指南（必须）
└── agent/
    └── manifest.json        # 机器可读命令注册表（必须）
```

### 15.3 SKILL.md 标准模板

采用 **Agent Skills** 格式（兼容 Hermes `~/.hermes/skills/` 与 OpenClaw Skill），**禁止**仅用自定义 YAML `commands:` 块。

**Frontmatter（必须）**：

```yaml
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
    - fetch-bilibili
    - intel-trending
  human_required_commands:
    - config-login-xiaohongshu
---
```

**正文结构（必须章节）**：

| 章节 | 内容 |
|------|------|
| 前置条件 | 安装命令、版本验证、Cookie 预配置说明 |
| Agent 推荐命令 | 每条含：完整 bash、参数说明、exit code、JSON 字段 |
| 长任务说明 | 哪些命令需 `spawn` / cron，禁止同步等待 |
| 禁止 Agent 调用 | login、写 cookie、未授权写入等 |
| 输出解析 | stdout=JSON，stderr=日志 |

**正文示例片段**：

    # social-monitor

    ## Agent 推荐命令

    采集微博热搜（agent_safe: true）：

        social-monitor fetch weibo-trending --count 20 --format json

    - 参数：`--count` 条数（默认 20）
    - 退出码：0 成功 / 2 无数据 / 3 采集失败
    - 输出字段：`items[].word`, `items[].hot_value`

    批量热榜增量：

        social-monitor intel trending --diff --format json

    ## 禁止 Agent 自动调用

    | 命令 | 原因 |
    |------|------|
    | `config login *` | 需人工扫码 |
    | `config cookie set` | 涉及凭证写入 |

**Hermes 安装**：

```bash
hermes skills install /path/to/social-monitor-CLI   # 目录含 SKILL.md
# 或复制到 ~/.hermes/skills/social-monitor/
```

**OpenClaw 调用**：

```bash
# Bash 工具
social-monitor fetch weibo-trending --count 20 --format json

# 后台任务
sessions_spawn(task="social-monitor intel trending --diff --format json", taskName="daily-trending")

# 定时（cron）
openclaw cron add --name "微博热搜" --command "social-monitor fetch weibo-trending --count 50 --format json" --schedule "0 9 * * *"
```

### 15.4 agent/manifest.json 规范

供 Task-platform、MCP 适配层、IDE 插件自动发现命令与参数 Schema。

```json
{
  "$schema": "https://compo.dev/schemas/cli-agent-manifest/v1",
  "name": "social-monitor",
  "version": "1.0.0",
  "cli": {
    "command": "social-monitor",
    "install": "pip install -e .",
    "verify": "./verify.sh"
  },
  "commands": [
    {
      "name": "fetch-weibo-trending",
      "description": "采集微博热搜榜",
      "cli_template": "social-monitor fetch weibo-trending --count {count} --format json",
      "agent_safe": true,
      "interactive": false,
      "timeout_sec": 120,
      "params": {
        "count": {
          "type": "integer",
          "default": 20,
          "minimum": 1,
          "maximum": 100,
          "description": "热搜条数"
        }
      },
      "output": {
        "format": "json",
        "schema_ref": "#/definitions/weibo_trending_response"
      },
      "exit_codes": {
        "0": "success",
        "2": "no_data",
        "3": "scrape_failed"
      }
    },
    {
      "name": "config-login-xiaohongshu",
      "description": "浏览器扫码登录小红书",
      "cli_template": "social-monitor config login xiaohongshu",
      "agent_safe": false,
      "interactive": true,
      "human_required": true,
      "reason": "需要人工扫码确认"
    },
    {
      "name": "monitor-live",
      "description": "直播开播检测与采集（长任务）",
      "cli_template": "social-monitor monitor run --task live",
      "agent_safe": "background_only",
      "interactive": false,
      "timeout_sec": 0,
      "spawn_hint": "sessions_spawn | cron | nohup",
      "reason": "阻塞式长任务，禁止 Agent 前台同步等待"
    }
  ],
  "definitions": {
    "weibo_trending_response": {
      "type": "object",
      "required": ["module", "data_source", "items"],
      "properties": {
        "module": { "const": "weibo-trending" },
        "data_source": { "enum": ["live", "demo", "cache"] },
        "count": { "type": "integer" },
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "word": { "type": "string" },
              "hot_value": { "type": "integer" }
            }
          }
        }
      }
    }
  }
}
```

| 字段 | 必须 | 说明 |
|------|------|------|
| `name` | ✓ | 与 SKILL.md frontmatter 一致 |
| `cli.command` | ✓ | 全局可执行命令名 |
| `commands[].name` | ✓ | 逻辑命令 ID（kebab-case） |
| `commands[].cli_template` | ✓ | 带 `{param}` 占位符的完整命令 |
| `commands[].agent_safe` | ✓ | 见 §15.5 |
| `commands[].params` | 推荐 | JSON Schema 风格参数定义 |
| `commands[].interactive` | ✓ | 是否需人工介入 |
| `commands[].timeout_sec` | 推荐 | Agent 侧超时；0 表示不限（长任务） |

### 15.5 agent_safe 命令分级

每个子命令必须在 `manifest.json` 与 `SKILL.md` frontmatter 中标注等级：

| 等级 | `agent_safe` 值 | 含义 | Agent 行为 |
|------|----------------|------|-----------|
| **A 安全** | `true` | 只读采集、查询、 `--demo`；无交互；有超时 | 可直接 Bash 调用 |
| **B 后台** | `background_only` | 长任务、daemon、阻塞监控 | 仅 `spawn` / cron / `nohup`，禁止同步等待 |
| **C 写入** | `write_with_confirm` | `--save`、`--force`、通知推送 | 需用户确认或任务单明确授权 |
| **D 禁止** | `false` | login、cookie 写入、破坏性操作 | **禁止** Agent 自动调用 |

**默认归类指南**（新建 CLI 时对照）：

| 命令类型 | 等级 | 示例 |
|---------|------|------|
| `fetch * --format json`（免登录源） | A | `fetch weibo-trending` |
| `fetch *` + 已配置 Cookie 的私密源 | A | `fetch weibo --uid xxx` |
| `* --demo` | A | `clauto miit --demo --format json` |
| `config check` / `monitor routes` | A | 只读诊断 |
| `intel trending --diff` | A | 批量只读 |
| `monitor run` / `start`（阻塞） | B | 直播监控 |
| `fetch * --save` / `notify *` | C | 写 DB、发飞书 |
| `config login` / `config cookie set` | D | 交互式凭证 |
| `init-db` / `migrate`（生产） | D | 破坏性 schema 变更 |

**verify.sh 补充**：至少对一条 `agent_safe: true` 命令跑 smoke（优先 `--demo` 或免登录源）。

### 15.6 MCP 接入（可选）

CLI 本身不暴露 HTTP。若需 SkillForge / 标准 MCP `tools/call`：

1. 在 `agent/` 下提供薄适配 `mcp_server.py`，读取 `manifest.json` 仅暴露 `agent_safe: true` 的命令
2. 或注册到 SkillForge Console，由 Skill 定义映射到 `cli_template`

MCP Tool 命名：`{cli_name}_{command_name}`，如 `social_monitor_fetch_weibo_trending`。

### 15.7 Agent 接入 Checklist

```
[ ] SKILL.md 使用 Agent Skills frontmatter（非纯 YAML commands 块）
[ ] agent/manifest.json 列出全部对外命令
[ ] 每条命令标注 agent_safe 四级之一
[ ] agent_safe:true 命令均有 params + timeout_sec
[ ] 交互式命令标记 human_required: true
[ ] SKILL.md 写明「禁止 Agent 调用」清单
[ ] verify.sh smoke 至少覆盖 1 条 agent_safe 命令
[ ] README 增加「Agent 接入」小节，链接 SKILL.md
```

---

## 16. 与 Compo 生态衔接

CLI 本身通常不暴露 HTTP，但若需联邦接入：

- 编排层（Task-platform）通过 `agent/manifest.json` 发现 CLI 能力，通过 `SKILL.md` 指导 Agent 执行
- MCP 类平台（SkillForge）读取 manifest 中 `agent_safe: true` 命令生成 Tool Schema
- 审计事件推送 safe-audit 时遵循 `audit-event-schema.json`
- 错误码若需跨服务传递，参考 [compo-standards/error-codes.md](../compo-standards/error-codes.md)

---

## 17. 新项目 Checklist

```
[ ] 目录名 {domain}-{purpose}-CLI
[ ] pyproject.toml + console_scripts 注册
[ ] {package}/cli.py 单一入口
[ ] --help / --version / -v / -q
[ ] --format json + 输出契约
[ ] --demo 或 MOCK 模式
[ ] exit code 0/1/2/3 语义文档化
[ ] .env.example + config.yaml.example
[ ] verify.sh 可离线通过
[ ] README 快速开始
[ ] guide/ 至少一篇设计或实战文档
[ ] .gitignore 含 .env、auth/、venv/
[ ] SKILL.md（Agent Skills 格式）
[ ] agent/manifest.json + agent_safe 分级
[ ] §15.7 Agent 接入 Checklist 全部勾选
```

---

## 18. 命令设计反模式

| 反模式 | 正确做法 |
|--------|---------|
| 要求 `python main.py` | `pip install -e .` + 全局命令 |
| 日志与 JSON 混 stdout | 日志 stderr，数据 stdout |
| 无 `--demo` 导致 verify 依赖外网 | 内置 fixture + mock 测试 |
| 密钥写死在代码 | .env + 环境变量 |
| 每个子命令不同输出格式 | 统一 `--format` |
| 失败一律 exit 1 | 区分无数据(2)与采集失败(3) |
| 无 verify.sh | 根目录一键验收 |
| SKILL 用自定义 YAML 无 frontmatter | Agent Skills 标准 + manifest.json |
| 未标注 agent_safe 让 Agent 调 login | manifest 标记 `human_required: true` |
| 长任务同步阻塞 Agent 会话 | `background_only` + spawn/cron 说明 |

---

## 19. 参考链接

- [Command Line Interface Guidelines (clig.dev)](https://clig.dev/)
- [12 Factor CLI Apps](https://12factor.net/)
- [Click Documentation](https://click.palletsprojects.com/)
- [Typer Documentation](https://typer.tiangolo.com/)
- [Hermes Agent Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [OpenClaw CLI Backends](https://docs.openclaw.ai/gateway/cli-backends)（LLM 推理后端，非业务 CLI）
- [Compo observability](../compo-standards/observability.md)
- [Compo verify-contract](../compo-standards/verify-contract.md)

---

*Last Updated: 2026-06-25*
