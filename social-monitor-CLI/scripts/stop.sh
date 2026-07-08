#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 停止 social-monitor 基础设施 ==="
docker compose down
echo "=== 已停止 ==="
