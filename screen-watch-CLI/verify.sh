#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/pip" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

echo "=== screen-watch 验证 ==="

echo "[1/5] 安装依赖..."
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
pip install -q -e ".[dev]"

echo "[2/5] CLI 基础..."
screen-watch --version
screen-watch --help > /dev/null
screen-watch monitor --help > /dev/null

echo "[3/5] 离线 demo + JSON 契约..."
RESULT=$(screen-watch monitor run --demo --format json)
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('module') == 'monitor-run'
assert d.get('data_source') == 'demo'
assert d.get('preset') == 'wechat-live'
assert 'events' in d and len(d['events']) >= 1
assert any(e.get('type') == 'metric' for e in d['events'])
assert any(e.get('type') == 'chat' for e in d['events'])
print('  ✓ monitor run --demo JSON 契约 OK')
"

echo "[4/5] JSONL 输出..."
LINES=$(screen-watch monitor run --demo --format jsonl | wc -l | tr -d ' ')
test "$LINES" -ge 1 && echo "  ✓ jsonl 输出 $LINES 行"

echo "[5/5] 单元测试..."
pytest -q tests/ 2>/dev/null && echo "  ✓ 单元测试 OK"

echo "=== 验证完成 ==="
