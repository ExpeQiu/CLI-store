#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "[!] 虚拟环境未初始化，请先运行: ./setup.sh"
  exit 1
fi

PORT="${VIDEO_EDIT_WEB_PORT:-8766}"
HOST="${VIDEO_EDIT_WEB_HOST:-0.0.0.0}"
PID_FILE="$PROJECT_ROOT/logs/web.pid"
LOG_FILE="$PROJECT_ROOT/logs/web.log"

mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/outputs" "$PROJECT_ROOT/uploads"

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    if curl -sf "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
      echo "[+] Web 服务已在运行 (PID=$OLD_PID)，端口 $PORT"
      exit 0
    fi
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

echo "[+] 安装 Web 依赖..."
"$PYTHON" -m pip install -q -e ".[web]" 2>/dev/null || "$PYTHON" -m pip install -q -e .

export VIDEO_EDIT_ROOT="$PROJECT_ROOT"
echo "[+] 启动 Web 服务 http://$HOST:$PORT"
nohup "$PYTHON" -m uvicorn video_edit.web.server:create_app \
  --factory \
  --host "$HOST" \
  --port "$PORT" \
  --timeout-keep-alive 120 \
  >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

for i in $(seq 1 15); do
  sleep 1
  if curl -sf "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
    echo "[+] 已启动 PID=$(cat "$PID_FILE")"
    echo "    访问: http://127.0.0.1:$PORT"
    exit 0
  fi
done

echo "[!] 启动超时，查看日志: $LOG_FILE"
tail -10 "$LOG_FILE"
exit 1
