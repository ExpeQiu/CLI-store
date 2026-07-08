#!/usr/bin/env bash
# screen-watch OCR → zhibo-monitor 入库 管道
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Zhibo_ROOT="$(cd "$ROOT/../zhibo-monitor-CLI" && pwd)"

if [[ -x "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

WINDOW="${SCREEN_WATCH_WINDOW:-微信}"
INTERVAL="${SCREEN_WATCH_INTERVAL:-1.5}"
EVENT_NAME="${Zhibo_EVENT_NAME:-微信客户端直播-OCR}"
CAR_BRAND="${Zhibo_CAR_BRAND:-unknown}"
ROOM_ID="${Zhibo_ROOM_ID:-wechat-ocr}"
CONFIG="${SCREEN_WATCH_CONFIG:-$ROOT/config.yaml}"

mkdir -p "$ROOT/logs"

echo "[pipeline] 初始化 zhibo-monitor 数据库..." >&2
(
  cd "$Zhibo_ROOT"
  if [[ -x .venv/bin/activate ]]; then source .venv/bin/activate; fi
  zhibo-monitor init-db
)

echo "[pipeline] 启动 OCR 监控 → ingest..." >&2
ARGS=(monitor run --window "$WINDOW" --interval "$INTERVAL" --format jsonl)
[[ -f "$CONFIG" ]] && ARGS+=(--config "$CONFIG")

screen-watch "${ARGS[@]}" | (
  cd "$Zhibo_ROOT"
  if [[ -x .venv/bin/activate ]]; then source .venv/bin/activate; fi
  zhibo-monitor ingest \
    --platform sph-client \
    --room-id "$ROOM_ID" \
    --event-name "$EVENT_NAME" \
    --car-brand "$CAR_BRAND"
)
