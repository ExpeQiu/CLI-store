---
name: screen-watch
description: "屏幕区域 OCR 直播监控 CLI。macOS Vision / PaddleOCR，主攻微信 Mac 客户端直播。监控无 DOM 的客户端直播、屏幕文字变化时激活。"
version: "0.3.0"
---

# screen-watch

屏幕区域 OCR 直播监控，与 zhibo-monitor 互补。

## 常用命令

```bash
screen-watch monitor run --window "微信" --format jsonl
screen-watch capture once --region viewer_count --window "微信" --save-crop logs/debug/viewer.png
screen-watch monitor run --demo
./scripts/e2e-smoke.sh
screen-watch monitor run --format jsonl | zhibo-monitor ingest --platform sph-client
```

## 依赖

```bash
pip install -e ".[capture,dev]"              # macOS Vision（Python 3.14 OK）
pip install -e ".[capture,ocr,dev]"          # + PaddleOCR（Python ≤3.13）
```

macOS 需屏幕录制权限。

## 文档

- `guide/TECHNICAL_DESIGN.md`
- `guide/微信客户端直播监控实战清单.md`
