#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${SM_PG_DATABASE:-social_monitor}"
DB_USER="${SM_PG_USER:-postgres}"
DB_HOST="${SM_PG_HOST:-localhost}"
DB_PORT="${SM_PG_PORT:-5432}"

echo "=== 初始化 PostgreSQL 数据库: ${DB_NAME} ==="

if command -v docker >/dev/null 2>&1 && docker compose ps postgres 2>/dev/null | grep -q "running"; then
  echo "检测到 docker compose postgres 已运行"
elif ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
  echo "PostgreSQL 未就绪，尝试启动 docker compose..."
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  (cd "$ROOT" && docker compose up -d postgres)
  sleep 3
fi

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE ${DB_NAME};"

echo "数据库 ${DB_NAME} 已就绪"
echo "请在 ~/.social-monitor/config.yaml 中配置 postgres 连接信息"
