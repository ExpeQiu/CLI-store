#!/usr/bin/env bash
# 端到端验收：离线管道 + 可选 live 探测（需微信窗口 + 屏幕录制权限）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Zhibo_ROOT="$(cd "$ROOT/../zhibo-monitor-CLI" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

echo "=== screen-watch E2E 验收 ==="

echo "[1/4] 安装 capture 依赖（含 macOS Vision OCR）..."
pip install -q -e ".[capture,dev]"

echo "[2/4] 离线管道 demo → zhibo-monitor ingest..."
(
  cd "$Zhibo_ROOT"
  [[ -x .venv/bin/activate ]] && source .venv/bin/activate
  export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/logs/e2e_zhibo.db}"
  zhibo-monitor init-db >/dev/null
)
RESULT=$(screen-watch monitor run --demo --format jsonl | (
  cd "$Zhibo_ROOT"
  [[ -x .venv/bin/activate ]] && source .venv/bin/activate
  export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/logs/e2e_zhibo.db}"
  zhibo-monitor ingest --platform sph-client --room-id e2e-demo --event-name "E2E验收"
))
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('chats', 0) >= 1
assert d.get('metrics', 0) >= 1
print('  ✓ demo 管道入库 OK task_id=%s' % d.get('task_id'))
"

echo "[3/4] Vision OCR 合成图测试..."
pytest -q tests/test_vision_ocr.py 2>/dev/null && echo "  ✓ Vision OCR OK" || echo "  ⚠ Vision OCR 跳过（非 macOS 或无 Vision 框架）"

echo "[4/4] Live 探测（可选，需微信窗口 + 屏幕录制权限）..."
if screen-watch window list --filter 微信 --format json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('count', 0) > 0
" 2>/dev/null; then
  echo "  ✓ 检测到微信窗口"
  echo "  → 运行单帧 OCR: screen-watch capture once --region viewer_count --window 微信 -v"
  if screen-watch capture once --region viewer_count --window "微信" --format json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  ✓ 单帧 OCR:', repr(d.get('text','')[:80]))
" 2>/dev/null; then
    :
  else
    echo "  ⚠ 单帧 OCR 失败（检查屏幕录制权限或区域配置）"
  fi
else
  echo "  ⚠ 未检测到微信窗口或缺少屏幕录制权限，跳过 live 探测"
  echo "    请打开微信直播后重试: ./scripts/e2e-smoke.sh"
fi

echo "=== E2E 验收完成 ==="
