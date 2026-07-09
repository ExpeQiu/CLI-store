#!/usr/bin/env bash
# 停止 Comfyui-CLI Web 控制台
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PID_FILE="$PROJECT_ROOT/logs/web.pid"
PORT="${COMFYUI_WEB_PORT:-8765}"

stopped=0

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "[+] 已停止 Web 服务 PID=$PID"
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

# 兜底：按端口清理残留进程
PORT_PID=$(lsof -ti ":${PORT}" 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
  kill $PORT_PID 2>/dev/null || true
  echo "[+] 已清理端口 ${PORT} 占用进程"
  stopped=1
fi

if [ "$stopped" -eq 0 ]; then
  echo "[*] Web 服务未运行"
fi
