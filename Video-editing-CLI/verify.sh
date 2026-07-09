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
CLI="$PROJECT_ROOT/.venv/bin/video-edit"
if [ -x "$CLI" ]; then
  echo ""
  echo "[+] video-edit --version"
  "$CLI" --version
  echo ""
  echo "[+] video-edit aroll run --demo"
  "$CLI" aroll run --demo --format json
  echo ""
  echo "[+] pytest"
  "$PYTHON" -m pytest tests/ -q
fi
