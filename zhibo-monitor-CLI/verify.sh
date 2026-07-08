#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/pip" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

# 离线验证默认 SQLite，避免依赖 PostgreSQL
export DATABASE_URL="${DATABASE_URL:-sqlite:///./zhibo_monitor_verify.db}"

echo "=== zhibo-monitor 验证 ==="

echo "[1/5] 安装..."
pip install -q -e ".[dev]" 2>/dev/null || python3 -m pip install -q -e ".[dev]" 2>/dev/null || python3 -m pip install -q -e .

echo "[2/5] CLI 基础..."
zhibo-monitor --version
zhibo-monitor --help > /dev/null

echo "[3/5] init-db..."
zhibo-monitor init-db

echo "[4/5] demo smoke..."
zhibo-monitor start bilibili 22603245 --demo | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('data_source') == 'demo'
assert d.get('platform') == 'bilibili'
print('  ✓ start --demo OK')
"

echo "[5/5] ingest --demo..."
zhibo-monitor ingest --demo | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('module') == 'ingest'
assert d.get('data_source') == 'demo'
assert d.get('metrics') == 1
assert d.get('chats') == 2
print('  ✓ ingest --demo OK')
"

pytest -q tests/test_ingest_screen_watch.py 2>/dev/null && echo "  ✓ ingest 单元测试 OK"

echo "=== 验证完成 ==="
