#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
  echo "[+] 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

echo "[+] 安装 video-edit-cli（editable）"
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e ".[dev]"

if [ ! -f "config.yaml" ] && [ -f "config.yaml.example" ]; then
  cp config.yaml.example config.yaml
  echo "[+] 已创建 config.yaml"
fi

echo "[+] 完成。下一步:"
echo "    ./verify.sh"
echo "    video-edit aroll run --demo"
