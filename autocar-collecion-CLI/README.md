# clauto

CLI automation toolkit - 工信部公告 / 汽车新闻 / 车型监测

## 安装

```bash
cd autocar-collecion-CLI

# 方式一：pip 安装（推荐）
pip install -e .

# 方式二：仅安装依赖
pip install -r requirements.txt
```

> **scrapling**（JS 渲染抓取）：`brew install scrapling`  
> 或通过环境变量指定路径：`export SCRAPLING_BIN=/path/to/scrapling`

## 快速验证

```bash
chmod +x verify.sh
./verify.sh
```

## 使用方法

```bash
# 工信部公告（演示模式）
python3 cli.py miit --demo

# 汽车新闻（需 TAVILY_API_KEY，或使用 --demo）
export TAVILY_API_KEY=your_key
python3 cli.py news --source industry --keyword 比亚迪

# 车型监测
python3 cli.py monitor -b 比亚迪 -m 海豹 --demo
python3 cli.py monitor -b 比亚迪 -m 海豹 \
  --competitors 特斯拉,Model 3,小米,SU7 --demo

# JSON 输出
python3 cli.py miit --demo --format json

# 详细日志
python3 cli.py -v miit --demo
```

## 命令概览

| 命令 | 说明 |
|------|------|
| `miit` | 抓取工信部公告 |
| `news` | 抓取汽车/新能源新闻 |
| `monitor` | 监测车型价格与配置 |

### 全局参数

| 参数 | 说明 |
|------|------|
| `-v, --verbose` | 详细日志（DEBUG） |
| `-q, --quiet` | 静默模式（仅 WARNING+） |

### miit

| 参数 | 说明 | 默认 |
|------|------|------|
| `--start` | 起始日期 YYYY-MM-DD | 最近7天 |
| `--end` | 结束日期 YYYY-MM-DD | 今天 |
| `--pages` | 最多翻页数 | 5 |
| `--format` | markdown / json | markdown |
| `--output, -o` | 输出文件 | stdout |
| `--demo` | 演示数据 | - |

### news

| 参数 | 说明 | 默认 |
|------|------|------|
| `--source` | industry / new-energy | industry |
| `--keyword, -k` | 关键词 | - |
| `--date, -d` | 日期 YYYY-MM-DD | - |
| `--max-results, -n` | 最大条数 | 10 |
| `--demo` | 演示数据 | - |

### monitor

| 参数 | 说明 | 默认 |
|------|------|------|
| `--brand, -b` | 品牌（必填） | - |
| `--model, -m` | 车型（必填） | - |
| `--competitors, -c` | 竞品：品牌1,车型1,... | - |
| `--baseline, -B` | 基线文件（对比用，不自动覆盖） | - |
| `--save-baseline` | 保存本次结果为基线 | - |
| `--source` | autohome / yiche | autohome |
| `--demo` | 演示数据 | - |

## 环境变量

| 变量 | 说明 |
|------|------|
| `TAVILY_API_KEY` | Tavily 新闻搜索 API Key |
| `SCRAPLING_BIN` | scrapling 可执行文件路径 |
| `CLAUTO_CACHE_DIR` | HTML 缓存目录（默认 `~/.clauto/cache`） |

## Exit Code

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 参数/逻辑错误 |
| 2 | 无数据 |
| 3 | 抓取失败 |

## 项目结构

```
autocar-collecion-CLI/
├── cli.py                 # 入口（薄包装）
├── pyproject.toml         # 包配置
├── verify.sh              # 验证脚本
├── requirements.txt
└── clauto/
    ├── cli.py             # CLI 主逻辑
    ├── config.py          # 配置与环境变量
    ├── fetch.py           # 统一抓取层
    ├── formatters.py      # JSON/Markdown 格式化
    ├── result.py          # ScrapeResult 封装
    ├── miit.py
    ├── news.py
    ├── monitor.py
    └── parsers/
        └── autohome.py    # 汽车之家解析器
```

## 数据来源标注

输出中会明确标注数据来源：
- `实时抓取` — 来自网络的真实数据
- `演示数据 [DEMO]` — `--demo` 模式的内置样例
- 无 Key / 抓取失败时不再静默混入演示数据

## 注意事项

- 数据源页面结构可能变化，选择器需定期维护
- scrapling 首次运行可能下载浏览器二进制
- 本工具仅供学习研究使用
