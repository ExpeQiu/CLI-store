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

"$PYTHON" scripts/verify_env.py "$@"
CLI="$PROJECT_ROOT/.venv/bin/comfyui"
if [ -x "$CLI" ]; then
  echo ""
  echo "[+] comfyui --version"
  "$CLI" --version
  echo ""
  echo "[+] comfyui workflow list"
  "$CLI" workflow list
fi

WEB_PORT="${COMFYUI_WEB_PORT:-8765}"
if curl -sf "http://127.0.0.1:${WEB_PORT}/api/ping" >/dev/null 2>&1; then
  echo ""
  echo "[+] Web API 验证 (port ${WEB_PORT})"
  COMFYUI_CLI_ENDPOINT="http://127.0.0.1:${WEB_PORT}" "$PYTHON" scripts/verify_web_api.py
else
  echo ""
  echo "[*] Web 服务未运行 (port ${WEB_PORT})，跳过 verify_web_api.py"
  echo "    启动: ./start-web.sh"
fi
