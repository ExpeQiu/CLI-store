#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
PASS=0
FAIL=0

log()  { echo "[verify] $*"; }
ok()   { log "✓ $*"; PASS=$((PASS + 1)); }
fail() { log "✗ $*"; FAIL=$((FAIL + 1)); }

log "安装依赖..."
if pip install -q -e . 2>/dev/null || python3 -m pip install -q -e . 2>/dev/null; then
    ok "pip install -e ."
else
    fail "pip install -e ."
fi

if clauto --version >/dev/null 2>&1; then
    ok "clauto --version"
else
    fail "clauto --version"
fi

if clauto --help >/dev/null 2>&1; then
    ok "clauto --help"
else
    fail "clauto --help"
fi

if clauto miit --demo 2>/dev/null | grep -q "工信部公告"; then
    ok "miit --demo 输出正常"
else
    fail "miit --demo 输出异常"
fi

if clauto miit --demo --format json 2>/dev/null | $PYTHON -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('module') == 'miit'
assert d.get('data_source') == 'demo'
assert 'announcements' in d
assert 'fetched_at' in d
"; then
    ok "JSON 输出契约 (miit)"
else
    fail "JSON 输出契约 (miit)"
fi

clauto miit --demo >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ok "miit --demo exit 0"
else
    fail "miit --demo exit code 非 0"
fi

echo ""
log "验证完成: ${PASS} 通过, ${FAIL} 失败"
[ "$FAIL" -eq 0 ] || exit 1
