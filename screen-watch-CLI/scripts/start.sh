#!/usr/bin/env bash
# 启动 screen-watch 监控（后台）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

mkdir -p logs
PID_FILE="logs/screen-watch.pid"
LOG_FILE="logs/screen-watch.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "screen-watch 已在运行 PID=$(cat "$PID_FILE")"
  exit 0
fi

WINDOW="${SCREEN_WATCH_WINDOW:-微信}"
INTERVAL="${SCREEN_WATCH_INTERVAL:-1.5}"
CONFIG="${SCREEN_WATCH_CONFIG:-config.yaml}"
SAVE_DB="${SCREEN_WATCH_DB:-logs/screen-watch.db}"

ARGS=(
  monitor run --preset wechat-live --window "$WINDOW" --interval "$INTERVAL"
  --format jsonl --save "$SAVE_DB" --require-foreground
)
[[ -f "$CONFIG" ]] && ARGS+=(--config "$CONFIG")

nohup screen-watch "${ARGS[@]}" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "screen-watch 已启动 PID=$(cat "$PID_FILE") log=$LOG_FILE"
