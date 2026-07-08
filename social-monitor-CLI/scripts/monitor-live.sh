#!/usr/bin/env bash
# 直播监控：B站开播直采 + 抖音 Octopus 入库
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${SM_LOG_DIR:-$HOME/.social-monitor/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/monitor-live-$(date +%Y%m%d).log"

exec >> >(tee -a "$LOG_FILE") 2>&1

echo "=== monitor-live $(date -Iseconds) ==="

if command -v social-monitor >/dev/null 2>&1; then
  social-monitor monitor run --task live "$@"
else
  pip install -q -e "$ROOT" 2>/dev/null || pip install -e "$ROOT"
  python -m social_monitor.cli monitor run --task live "$@"
fi

echo "=== done ==="
