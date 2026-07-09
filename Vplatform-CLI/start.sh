#!/usr/bin/env bash
# 启动 Web 控制台（FastAPI + 静态页）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${VPLATFORM_API_HOST:-127.0.0.1}"
PORT="${VPLATFORM_API_PORT:-8768}"
PID_FILE="$SCRIPT_DIR/logs/web.pid"
LOG_FILE="$SCRIPT_DIR/logs/web.log"
FG=0

if [ "${1:-}" = "--fg" ] || [ "${1:-}" = "-f" ]; then
  FG=1
fi

mkdir -p logs

export VPLATFORM_API_HOST="$HOST"
export VPLATFORM_API_PORT="$PORT"

PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "[!] 虚拟环境未初始化，请先运行: ./setup.sh"
  exit 1
fi

# 前台模式：适合本地终端长期运行
if [ "$FG" -eq 1 ]; then
  echo "[+] 前台启动 http://${HOST}:${PORT}/ （Ctrl+C 停止）"
  echo "[+] 日志同时写入: $LOG_FILE"
  exec "$PYTHON" "$SCRIPT_DIR/scripts/api_server.py" 2>&1 | tee -a "$LOG_FILE"
fi

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    if curl -sf "http://${HOST}:${PORT}/api/v1/health" >/dev/null 2>&1; then
      echo "[+] Web 已在运行 http://${HOST}:${PORT}/ (pid=$pid)"
      exit 0
    fi
    echo "[*] 清理无响应进程 pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  if ! curl -sf "http://${HOST}:${PORT}/api/v1/health" >/dev/null 2>&1; then
    echo "[!] 端口 ${PORT} 已被占用，请执行 ./stop.sh 或设置 VPLATFORM_API_PORT"
    lsof -i ":${PORT}" 2>/dev/null | head -5 || true
    exit 1
  fi
fi

nohup "$PYTHON" "$SCRIPT_DIR/scripts/api_server.py" >>"$LOG_FILE" 2>&1 &
pid=$!
disown "$pid" 2>/dev/null || true
echo "$pid" >"$PID_FILE"

for _ in $(seq 1 20); do
  if curl -sf "http://${HOST}:${PORT}/api/v1/health" >/dev/null 2>&1; then
    echo "[+] Web 已启动 http://${HOST}:${PORT}/"
    echo "[+] PID=$pid  日志: $LOG_FILE"
    echo "[*] 若页面无法访问，请在终端执行: ./start.sh --fg"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "[!] 进程已退出，查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    tail -15 "$LOG_FILE"
    exit 1
  fi
  sleep 0.3
done

echo "[!] 启动超时，请查看日志: $LOG_FILE"
tail -10 "$LOG_FILE"
exit 1
