#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 启动 social-monitor 基础设施 ==="
docker compose up -d postgres redis rsshub

echo "等待 PostgreSQL..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U postgres -d social_monitor >/dev/null 2>&1; then
    echo "PostgreSQL 就绪"
    break
  fi
  sleep 1
done

if [[ -x "$ROOT/scripts/init-db.sh" ]]; then
  bash "$ROOT/scripts/init-db.sh" || true
fi

echo "=== 基础设施已启动 ==="
docker compose ps
