#!/usr/bin/env bash
# 停止 Web 控制台
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${VPLATFORM_API_PORT:-8768}"
PID_FILE="$SCRIPT_DIR/logs/web.pid"
stopped=0

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "[+] 已停止 Web (pid=$pid)"
    stopped=1
  fi
  rm -f "$PID_FILE"
fi

# 兜底：按端口清理 api_server 残留
for p in $(lsof -ti ":${PORT}" 2>/dev/null || true); do
  cmd=$(ps -p "$p" -o command= 2>/dev/null || true)
  if echo "$cmd" | grep -q "api_server.py"; then
    kill "$p" 2>/dev/null || true
    echo "[+] 已清理端口 ${PORT} 进程 pid=$p"
    stopped=1
  fi
done

if [ "$stopped" -eq 0 ]; then
  echo "[-] Web 未运行"
fi
