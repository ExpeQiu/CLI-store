# Vplatform-CLI 2.1

精简版 **分镜驱动短视频编排 CLI**（无 Web/API、无 Wan POC 脚本依赖）。核心包名仍为 `vplatform`，面向 OpenClaw + ComfyUI 本地或隧道部署。

## 快速开始

```bash
./setup.sh
cp config.example.yaml config.yaml   # 配置 LLM / ComfyUI
./verify.sh
vplatform init --cwd
```

## CLI

```bash
vplatform --version
vplatform health
vplatform config validate
vplatform workflow list
vplatform status                    # ComfyUI 连通性（使用 vplatform.services.comfyui）

vplatform pipeline run -t "产品展示" --stop-at storyboard
vplatform task list
vplatform task status <task_id>
```

简写：`vplatform -t "主题" --stop-at storyboard` 等价于 `pipeline run`。

## OpenClaw

```bash
./scripts/sync_openclaw_skill.sh
./scripts/openclaw.sh status
./scripts/openclaw.sh pipeline run -t "主题" --stop-at storyboard
```

环境变量 `VPLATFORM_ROOT` 由 `openclaw.sh` 自动设置。

## 目录

| 路径 | 说明 |
|------|------|
| `vplatform/` | 核心 SDK（config、pipelines、services、cli） |
| `workflows/` | `flux_txt2img`、`wan2.1_txt2img`、`wan2.1_img2vid` |
| `prompts/storyboard.txt` | 分镜提示词模板 |
| `scripts/` | `openclaw.sh`、`verify_env.py`、`sync_openclaw_skill.sh` |

## AutoDL 隧道（可选）

在 `config.yaml` 的 `provider.autodl_tunnel_script` 中填写脚本路径（如 `scripts/autodl-tunnel.sh`）；留空则仅检测本地/商用 endpoint。
