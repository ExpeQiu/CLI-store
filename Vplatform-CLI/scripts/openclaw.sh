#!/usr/bin/env bash
# OpenClaw 包装：固定 VPLATFORM_ROOT 并调用 vplatform CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export VPLATFORM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VP_BIN="${VPLATFORM_ROOT}/.venv/bin/vplatform"
if [ ! -x "$VP_BIN" ]; then
  echo "[!] 未找到 $VP_BIN，请先运行: $VPLATFORM_ROOT/setup.sh" >&2
  exit 1
fi

exec "$VP_BIN" "$@"
