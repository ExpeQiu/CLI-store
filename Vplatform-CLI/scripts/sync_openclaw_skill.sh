#!/usr/bin/env bash
# 将 Vplatform-CLI 同步到 OpenClaw comfyui-video skill（vplatform CLI，无 POC/API）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="${OPENCLAW_SKILL_DIR:-$HOME/.openclaw/skills/comfyui-video}"

log() { echo "[sync] $*"; }

mkdir -p "$SKILL_DIR"/{scripts,workflows,prompts,vplatform,data/workflows,data/prompts,data/bgm}

# 入口与验证脚本
for f in openclaw.sh verify_env.py; do
  cp -f "$PROJECT_ROOT/scripts/$f" "$SKILL_DIR/scripts/$f"
  chmod +x "$SKILL_DIR/scripts/$f" 2>/dev/null || true
  log "scripts/$f"
done

# 核心 Python 包
rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '._*' \
  "$PROJECT_ROOT/vplatform/" "$SKILL_DIR/vplatform/"
log "vplatform/ (package)"

# 工作流与提示词
cp -f "$PROJECT_ROOT/workflows/"*.json "$SKILL_DIR/workflows/" 2>/dev/null || true
log "workflows/*.json"

if [[ -d "$PROJECT_ROOT/prompts" ]]; then
  cp -f "$PROJECT_ROOT/prompts/"* "$SKILL_DIR/prompts/" 2>/dev/null || true
  log "prompts/"
fi

# 配置模板
cp -f "$PROJECT_ROOT/config.example.yaml" "$SKILL_DIR/config.example.yaml"
log "config.example.yaml"

# Skill 根目录 CLI 入口（与 scripts/openclaw.sh 相同）
cp -f "$PROJECT_ROOT/scripts/openclaw.sh" "$SKILL_DIR/vplatform.sh"
chmod +x "$SKILL_DIR/vplatform.sh"
log "vplatform.sh (OpenClaw 入口)"

cat > "$SKILL_DIR/config.yaml" <<YAML
vplatform_root: "${PROJECT_ROOT}"

comfyui:
  url: "http://127.0.0.1:8188"
  output_dir: "output/"

vplatform:
  root: "${PROJECT_ROOT}"
  venv_python: "${PROJECT_ROOT}/.venv/bin/python"
  cli: "${PROJECT_ROOT}/.venv/bin/vplatform"

output:
  dir: "${PROJECT_ROOT}/outputs/"
  format: "mp4"
YAML
log "config.yaml"

cat > "$SKILL_DIR/SKILL.md" <<'SKILL_EOF'
# comfyui-video (Vplatform-CLI)

使用项目内 `vplatform` CLI 做分镜驱动短视频编排，勿使用已废弃的 `pipeline.py` / `comfyui_job.py`。

## 前置

- 在 `vplatform_root` 执行 `./setup.sh`，配置 `config.yaml`（LLM + ComfyUI）
- 入口：`$SKILL_DIR/vplatform.sh` 或 `$SKILL_DIR/scripts/openclaw.sh`（自动设置 `VPLATFORM_ROOT`）

## 常用命令

```bash
./vplatform.sh --version
./vplatform.sh health
./vplatform.sh config validate
./vplatform.sh workflow list
./vplatform.sh status

./vplatform.sh pipeline run -t "主题" --stop-at storyboard
./vplatform.sh pipeline run -t "主题" --stop-at final --profile fast

./vplatform.sh task list
./vplatform.sh task status <task_id>
```

简写：`./vplatform.sh -t "主题" --stop-at storyboard` 等价于 `pipeline run`。

## 同步

在 Vplatform-CLI 仓库根目录运行：`./scripts/sync_openclaw_skill.sh`
SKILL_EOF
log "SKILL.md"

log "同步完成 → $SKILL_DIR"
log "OpenClaw 示例:"
log "  $SKILL_DIR/vplatform.sh health"
log "  $SKILL_DIR/vplatform.sh pipeline run -t \"产品展示\" --stop-at storyboard"
log "  $SKILL_DIR/vplatform.sh task list"
