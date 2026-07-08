#!/usr/bin/env bash
# 每日监控任务 — 优先调用 social-monitor monitor run，回退到直接 CLI
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${SM_LOG_DIR:-$HOME/.social-monitor/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/monitor-daily-$(date +%Y%m%d).log"

exec >> >(tee -a "$LOG_FILE") 2>&1

echo "=== monitor-daily $(date -Iseconds) ==="

if command -v social-monitor >/dev/null 2>&1; then
  social-monitor monitor run --task daily "$@"
else
  pip install -q -e "$ROOT" 2>/dev/null || pip install -e "$ROOT"
  python -m social_monitor.cli monitor run --task daily "$@"
fi

echo "=== done ==="
