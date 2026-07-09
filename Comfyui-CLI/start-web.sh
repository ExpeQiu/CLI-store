#!/usr/bin/env bash
# 启动 Comfyui-CLI Web 控制台
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "[!] 虚拟环境未初始化，请先运行: ./setup.sh"
  exit 1
fi

PORT="${COMFYUI_WEB_PORT:-8765}"
HOST="${COMFYUI_WEB_HOST:-0.0.0.0}"
PID_FILE="$PROJECT_ROOT/logs/web.pid"
LOG_FILE="$PROJECT_ROOT/logs/web.log"

mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/outputs"

# 清理失效 PID
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    if curl -sf "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
      echo "[+] Web 服务已在运行 (PID=$OLD_PID)，端口 $PORT"
      echo "    访问: http://127.0.0.1:$PORT"
      exit 0
    fi
    echo "[*] 清理无响应进程 PID=$OLD_PID"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# 端口被 Vplatform-CLI 等其它服务占用
if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  if ! curl -sf "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
    echo "[!] 端口 ${PORT} 已被其他服务占用（非 Comfyui-CLI）"
    echo "    若 Vplatform-CLI 在运行: cd ../Vplatform-CLI && ./stop.sh"
    echo "    或设置 COMFYUI_WEB_PORT=8767 ./start-web.sh"
    lsof -i ":${PORT}" 2>/dev/null | head -5 || true
    exit 1
  fi
fi

echo "[+] 安装 Web 依赖..."
"$PYTHON" -m pip install -q -e ".[web]" 2>/dev/null || "$PYTHON" -m pip install -q -e .

echo "[+] 启动 Web 服务 http://$HOST:$PORT"
nohup "$PYTHON" -m uvicorn comfyui.web.server:create_app \
  --factory \
  --host "$HOST" \
  --port "$PORT" \
  --timeout-keep-alive 120 \
  >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

# 等待服务就绪（最多 15 秒）
for i in $(seq 1 15); do
  sleep 1
  if curl -sf "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
    echo "[+] 已启动 PID=$(cat "$PID_FILE")"
    echo "    访问: http://127.0.0.1:$PORT"
    echo "    日志: $LOG_FILE"
    exit 0
  fi
  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[!] 进程已退出，查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    tail -20 "$LOG_FILE"
    exit 1
  fi
done

echo "[!] 启动超时，进程可能仍在初始化，查看日志: $LOG_FILE"
tail -10 "$LOG_FILE"
