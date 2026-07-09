#!/usr/bin/env bash
# 初始化 Python 虚拟环境
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
  echo "[+] 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

echo "[+] 安装 comfyui-cli 包（editable）"
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e .

if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
  cp config.example.yaml config.yaml
  echo "[+] 已创建 config.yaml（请配置 ComfyUI endpoint）"
fi

mkdir -p data/workflows outputs logs

echo "[+] 完成。下一步:"
echo "    ./verify.sh"
echo "    comfyui workflow list"
echo "    comfyui image t2i -t \"红苹果\" -o ./outputs"
