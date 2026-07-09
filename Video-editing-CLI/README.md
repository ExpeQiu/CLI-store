# Video-editing-CLI

AI 辅助 A-Roll 口播初剪 CLI。输入原始视频 + 定稿脚本，输出可导入达芬奇 / Final Cut Pro 的 FCPXML 时间轴。

## 安装

```bash
./setup.sh
source .venv/bin/activate
```

可选依赖：

```bash
pip install -e ".[whisper]"      # faster-whisper 转录
pip install -e ".[whisperx]"     # WhisperX 强制对齐（中文精度）
pip install -e ".[web]"          # FastAPI Web API
```

## Web API（DSC3 集成）

```bash
./start-web.sh   # http://127.0.0.1:8766
./stop.sh
```

环境变量：`VIDEO_EDIT_WEB_PORT` · `VIDEO_EDIT_CLI_ROOT` · `VIDEO_EDIT_ENDPOINT`

## 快速开始

```bash
# Mock 验收
video-edit aroll run --demo

# 完整初剪
video-edit aroll run --video raw.mp4 --script script.txt -o outputs

# 分阶段
video-edit aroll transcribe --video raw.mp4 -o outputs/transcript.json
video-edit aroll align --transcript outputs/transcript.json --script script.txt
video-edit aroll export --decisions outputs/edit_decisions.json --video raw.mp4

# Multicam 同步
video-edit multicam sync --primary cam_a.mp4 --secondary cam_b.mp4 -o sync_map.json

# 批量 + 断点续跑
video-edit batch init -o batch.json
video-edit batch run batch.json -o outputs --resume
```

## 流水线阶段

```
extract → transcribe → [whisperx] → align → refine → export
```

| 阶段 | 说明 |
|------|------|
| transcribe | faster-whisper 逐词转录 |
| whisperx | 可选，强制对齐刷新词级时间戳 |
| align | WISP-COPY 脚本匹配 + 重复 take / 口误标记 |
| refine | ffmpeg 静音检测 + 0.4s 气口 + 长停顿切分 |
| export | FCPXML 1.11 + SRT |

## 配置亮点（config.yaml）

```yaml
transcribe:
  use_whisperx_align: false   # 中文口播建议 true

align:
  match_threshold: 0.55
  ambiguous_low: 0.40
  use_llm_review: false       # 需 OPENAI_API_KEY

pipeline:
  breath_gap_sec: 0.4
  long_pause_sec: 1.5
  silence_threshold_db: -40
```

## 验收

```bash
./verify.sh
```

## 文档

- [A-Roll 剪辑方案](./guide/A-Roll剪辑方案.md)
