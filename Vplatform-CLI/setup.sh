#!/usr/bin/env bash
# 初始化 Python 虚拟环境（CLI 版）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
  echo "[+] 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

echo "[+] 安装 vplatform 包（editable）"
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -e .

if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
  cp config.example.yaml config.yaml
  echo "[+] 已创建 config.yaml（请配置 LLM / ComfyUI）"
fi

echo "[+] 完成。下一步:"
echo "    ./verify.sh"
echo "    vplatform init --cwd"
echo "    vplatform pipeline run -t \"主题\" --stop-at storyboard"
