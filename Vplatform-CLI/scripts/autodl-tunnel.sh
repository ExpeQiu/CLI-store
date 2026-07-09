#!/usr/bin/env bash
# AutoDL SSH 隧道 — 将远程 ComfyUI (6006) 映射到本地 8188
# 配置: docs/m.md（首行 ssh 命令，末行密码）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/autodl-tunnel.log"
CONFIG_FILE="${AUTODL_CONFIG:-$PROJECT_ROOT/docs/m.md}"
LOCAL_PORT="${AUTODL_LOCAL_PORT:-8188}"
REMOTE_PORT="${AUTODL_REMOTE_PORT:-6006}"

mkdir -p "$LOG_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

parse_config() {
  if [ ! -f "$CONFIG_FILE" ]; then
    log "配置文件不存在: $CONFIG_FILE"
    log "请创建 docs/m.md：首行 ssh 命令，末行密码（参考 guide/算力服务器.md）"
    exit 1
  fi

  local ssh_line
  ssh_line=$(grep -E '^ssh ' "$CONFIG_FILE" | head -1)
  if [ -z "$ssh_line" ]; then
    log "未在 $CONFIG_FILE 中找到 ssh 登录行"
    exit 1
  fi

  SSH_PORT=$(echo "$ssh_line" | sed -n 's/.*-p[[:space:]]*\([0-9]*\).*/\1/p')
  SSH_HOST=$(echo "$ssh_line" | sed -n 's/.*root@\([^[:space:]]*\).*/\1/p')
  SSH_PASS=$(tail -1 "$CONFIG_FILE")

  if [ -z "$SSH_PORT" ] || [ -z "$SSH_HOST" ] || [ -z "$SSH_PASS" ]; then
    log "解析失败: port=$SSH_PORT host=$SSH_HOST"
    exit 1
  fi
}

tunnel_running() {
  pgrep -f "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" >/dev/null 2>&1
}

start_tunnel() {
  if tunnel_running; then
    log "隧道已存在: localhost:${LOCAL_PORT} -> ${SSH_HOST}:${REMOTE_PORT}"
    return 0
  fi

  if ! command -v sshpass >/dev/null 2>&1; then
    log "未安装 sshpass，请手动执行:"
    log "  ssh -p ${SSH_PORT} -L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT} root@${SSH_HOST}"
    exit 1
  fi

  local pass_file
  pass_file=$(mktemp)
  printf '%s' "$SSH_PASS" > "$pass_file"
  chmod 600 "$pass_file"

  log "建立隧道: localhost:${LOCAL_PORT} -> ${SSH_HOST}:${REMOTE_PORT} (ssh -p ${SSH_PORT})"
  if sshpass -f "$pass_file" ssh \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
    -p "$SSH_PORT" "root@${SSH_HOST}" \
    -N -f 2>>"$LOG_FILE"; then
    rm -f "$pass_file"
    sleep 1
    log "隧道已启动"
    return 0
  fi

  rm -f "$pass_file"
  log "隧道建立失败，请检查 docs/m.md 中的密码与网络"
  exit 1
}

stop_tunnel() {
  if tunnel_running; then
    pkill -f "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" || true
    log "隧道已关闭"
  else
    log "无运行中的隧道"
  fi
}

status_tunnel() {
  if curl -sf --connect-timeout 3 "http://127.0.0.1:${LOCAL_PORT}/system_stats" >/dev/null 2>&1; then
    log "ComfyUI 可访问: http://127.0.0.1:${LOCAL_PORT}"
    return 0
  fi
  if tunnel_running; then
    log "隧道进程存在，但 ComfyUI API 未响应（远程 ComfyUI 可能未启动）"
    return 1
  fi
  log "隧道未建立"
  return 1
}

log "=== autodl-tunnel.sh ==="
parse_config

case "${1:-start}" in
  start)
    start_tunnel
    status_tunnel || log "隧道已建立，等待远程 ComfyUI 就绪"
    ;;
  stop) stop_tunnel ;;
  status) status_tunnel ;;
  restart) stop_tunnel; start_tunnel; status_tunnel ;;
  *)
    echo "用法: $0 [start|stop|status|restart]"
    exit 1
    ;;
esac
