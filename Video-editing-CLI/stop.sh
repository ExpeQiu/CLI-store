#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/web.pid"
PORT="${VIDEO_EDIT_WEB_PORT:-8766}"

if [ ! -f "$PID_FILE" ]; then
  echo "[*] 未找到 PID 文件，尝试按端口停止"
  if lsof -ti ":${PORT}" >/dev/null 2>&1; then
    kill $(lsof -ti ":${PORT}") 2>/dev/null || true
    echo "[+] 已停止端口 $PORT 上的进程"
  else
    echo "[*] Web 服务未运行"
  fi
  exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "[+] 已停止 Web 服务 PID=$PID"
else
  echo "[*] 进程 $PID 不存在"
fi
rm -f "$PID_FILE"
