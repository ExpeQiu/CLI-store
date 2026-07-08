#!/usr/bin/env bash
# 批量解析 P0 account_id：自动提示抖音/小红书登录，输出 monitor.yaml 片段
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SM="${SM_CMD:-python3 -m social_monitor.cli}"
OUT_YAML="${RESOLVE_OUT:-data/p0-account-ids.yaml}"
OUT_JSON="${RESOLVE_JSON:-data/p0-account-ids.json}"
APPLY=()
if [[ "${APPLY_REGISTRY:-}" == "1" ]]; then
  APPLY=(--apply)
fi

mkdir -p data

echo "=========================================="
echo " P0 账号 ID 批量解析"
echo "------------------------------------------"
echo " 无需登录: B站 / 公众号"
echo " 需要登录: 抖音 / 小红书（将提示打开浏览器）"
echo " 输出: $OUT_YAML / $OUT_JSON"
echo "=========================================="
echo ""

"$SM" account resolve-p0 \
  --safe \
  --login \
  --output json \
  --out-file "$OUT_JSON" \
  "${APPLY[@]}"

python3 - <<PY
import json
from pathlib import Path
from social_monitor.account.resolvers import build_monitor_yaml_snippet

src = Path("${OUT_JSON}")
dst = Path("${OUT_YAML}")
results = json.loads(src.read_text(encoding="utf-8"))
dst.write_text(build_monitor_yaml_snippet(results), encoding="utf-8")
PY

echo ""
echo "[resolve-p0] JSON  -> $OUT_JSON"
echo "[resolve-p0] YAML  -> $OUT_YAML"
if [[ "${APPLY_REGISTRY:-}" == "1" ]]; then
  echo "[resolve-p0] 已写回 guide/监控渠道-账号.md"
fi
echo "[resolve-p0] 完成"
