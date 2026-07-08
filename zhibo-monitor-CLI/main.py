#!/usr/bin/env python3
"""兼容入口：请优先使用 zhibo-monitor 命令"""
from zhibo_monitor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
