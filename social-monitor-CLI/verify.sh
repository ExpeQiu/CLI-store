#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== social-monitor 验证 ==="

echo "[1/6] 安装依赖..."
pip install -q -e ".[dev]" 2>/dev/null || python3 -m pip install -q -e ".[dev]" 2>/dev/null || python3 -m pip install -q -e .

echo "[2/6] CLI 基础..."
social-monitor --version
social-monitor --help > /dev/null
social-monitor fetch --help > /dev/null

echo "[3/6] 离线 demo + JSON 契约..."
RESULT=$(social-monitor fetch weibo-trending --count 3 --format json --demo)
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('module') == 'weibo-trending'
assert d.get('data_source') == 'demo'
assert 'items' in d and len(d['items']) == 3
print('  ✓ weibo-trending --demo JSON 契约 OK')
"

echo "[4/6] 单元测试..."
pytest -q tests/test_wechat.py tests/test_monitor_runner.py tests/test_weibo_trending_date.py 2>/dev/null
echo "  ✓ 核心单元测试 OK"

echo "[5/6] 微信公众号 Mock 链路..."
pytest -q tests/test_wechat.py 2>/dev/null && echo "  ✓ 微信 Mock OK"

echo "[6/6] 外网冒烟（失败不阻断）..."
if social-monitor fetch weibo-trending --count 2 --format json 2>/dev/null | grep -q '"word"'; then
  echo "  ✓ 微博热搜 live OK"
else
  echo "  ⚠ 微博热搜 live 跳过（网络/API 不可用）"
fi

echo "=== 验证完成 ==="
