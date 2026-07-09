"""Demo 模式 Mock 数据。"""

from __future__ import annotations

from pathlib import Path

from video_edit.models.transcript import Transcript, TranscriptSegment, WordToken

DEMO_SCRIPT = """# Demo 口播脚本
今天我们来聊聊 AI 辅助剪辑。
它能大幅缩短 A-Roll 初剪时间。
我们只需要提供原始视频和定稿脚本。
系统会自动生成 FCPXML 时间轴。
"""

DEMO_TRANSCRIPT = Transcript(
    language="zh",
    duration_sec=42.0,
    source="demo",
    words=[
        WordToken(text="嗯", start=0.5, end=0.8),
        WordToken(text="今天", start=1.0, end=1.3),
        WordToken(text="我们", start=1.3, end=1.5),
        WordToken(text="来", start=1.5, end=1.65),
        WordToken(text="聊聊", start=1.65, end=1.95),
        WordToken(text="AI", start=1.95, end=2.2),
        WordToken(text="辅助", start=2.2, end=2.5),
        WordToken(text="剪辑", start=2.5, end=2.85),
        # 重复 take
        WordToken(text="今天", start=4.0, end=4.3),
        WordToken(text="我们", start=4.3, end=4.5),
        WordToken(text="来", start=4.5, end=4.65),
        WordToken(text="聊聊", start=4.65, end=4.95),
        WordToken(text="AI", start=4.95, end=5.2),
        WordToken(text="辅助", start=5.2, end=5.5),
        WordToken(text="视频", start=5.5, end=5.8),
        WordToken(text="剪辑", start=5.8, end=6.1),
        # 正确 take
        WordToken(text="今天", start=8.0, end=8.3),
        WordToken(text="我们", start=8.3, end=8.5),
        WordToken(text="来", start=8.5, end=8.65),
        WordToken(text="聊聊", start=8.65, end=8.95),
        WordToken(text="AI", start=8.95, end=9.2),
        WordToken(text="辅助", start=9.2, end=9.5),
        WordToken(text="剪辑", start=9.5, end=9.85),
        WordToken(text="它", start=12.0, end=12.2),
        WordToken(text="能", start=12.2, end=12.35),
        WordToken(text="大幅", start=12.35, end=12.65),
        WordToken(text="缩短", start=12.65, end=12.95),
        WordToken(text="A-Roll", start=12.95, end=13.3),
        WordToken(text="初剪", start=13.3, end=13.6),
        WordToken(text="时间", start=13.6, end=13.95),
        WordToken(text="我们", start=18.0, end=18.25),
        WordToken(text="只需要", start=18.25, end=18.6),
        WordToken(text="提供", start=18.6, end=18.85),
        WordToken(text="原始", start=18.85, end=19.15),
        WordToken(text="视频", start=19.15, end=19.4),
        WordToken(text="和", start=19.4, end=19.55),
        WordToken(text="定稿", start=19.55, end=19.85),
        WordToken(text="脚本", start=19.85, end=20.2),
        WordToken(text="系统", start=25.0, end=25.3),
        WordToken(text="会", start=25.3, end=25.45),
        WordToken(text="自动", start=25.45, end=25.75),
        WordToken(text="生成", start=25.75, end=26.05),
        WordToken(text="FCPXML", start=26.05, end=26.5),
        WordToken(text="时间轴", start=26.5, end=26.95),
    ],
    segments=[
        TranscriptSegment(id=0, start=1.0, end=2.85, text="今天我们来聊聊AI辅助剪辑"),
        TranscriptSegment(id=1, start=8.0, end=9.85, text="今天我们来聊聊AI辅助剪辑"),
        TranscriptSegment(id=2, start=12.0, end=13.95, text="它能大幅缩短A-Roll初剪时间"),
        TranscriptSegment(id=3, start=18.0, end=20.2, text="我们只需要提供原始视频和定稿脚本"),
        TranscriptSegment(id=4, start=25.0, end=26.95, text="系统会自动生成FCPXML时间轴"),
    ],
)


def write_demo_script(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEMO_SCRIPT, encoding="utf-8")
    return path
