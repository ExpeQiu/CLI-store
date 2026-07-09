"""FCPXML 1.11 导出。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from xml.dom import minidom

from loguru import logger

from video_edit.config import ExportConfig, PipelineConfig
from video_edit.models.edit_decision import EditDecision, EditClip


def _media_uri(path: Path, style: str) -> str:
    resolved = path.expanduser().resolve()
    if style == "relative":
        return resolved.name
    return "file://" + quote(resolved.as_posix())


def _sec_to_fcpxml(sec: float, frame_rate: float) -> str:
    frames = round(sec * frame_rate)
    denom = int(frame_rate * 100)
    num = frames * 100
    return f"{num}/{denom}s"


def _pretty_xml(element: ET.Element) -> str:
    rough = ET.tostring(element, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding=None)


def export_fcpxml(
    decision: EditDecision,
    video_path: Path,
    output_path: Path,
    *,
    pipeline_config: PipelineConfig,
    export_config: ExportConfig,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    frame_rate = decision.frame_rate or pipeline_config.frame_rate
    keep_clips = decision.keep_clips()
    if not keep_clips:
        raise ValueError("无保留片段，无法导出 FCPXML")

    total_output = sum(c.source_out - c.source_in for c in keep_clips)
    media_uri = _media_uri(video_path, export_config.media_path_style)

    fcpxml = ET.Element("fcpxml", version=export_config.fcpxml_version)
    resources = ET.SubElement(fcpxml, "resources")

    frame_denom = int(frame_rate * 100)
    fmt = ET.SubElement(
        resources,
        "format",
        id="r1",
        name=f"FFVideoFormat1080p{frame_rate:.0f}",
        frameDuration=f"100/{frame_denom}s",
        width=str(width),
        height=str(height),
    )
    _ = fmt  # noqa: F841

    asset_duration = _sec_to_fcpxml(decision.total_source_sec or total_output, frame_rate)
    asset = ET.SubElement(
        resources,
        "asset",
        id="r2",
        name=video_path.name,
        src=media_uri,
        start="0s",
        duration=asset_duration,
        hasVideo="1",
        hasAudio="1",
        format="r1",
    )
    _ = asset

    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name="A-Roll Edit")
    project = ET.SubElement(event, "project", name="Timeline")
    sequence = ET.SubElement(
        project,
        "sequence",
        format="r1",
        duration=_sec_to_fcpxml(total_output, frame_rate),
        tcStart="0s",
        tcFormat="NDF",
    )
    spine = ET.SubElement(sequence, "spine")

    timeline_offset = 0.0
    for clip in keep_clips:
        duration_sec = clip.source_out - clip.source_in
        ET.SubElement(
            spine,
            "asset-clip",
            ref="r2",
            name=clip.id,
            offset=_sec_to_fcpxml(timeline_offset, frame_rate),
            start=_sec_to_fcpxml(clip.source_in, frame_rate),
            duration=_sec_to_fcpxml(duration_sec, frame_rate),
            tcFormat="NDF",
        )
        timeline_offset += duration_sec

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + _pretty_xml(fcpxml)
    output_path.write_text(content, encoding="utf-8")
    logger.info("FCPXML 已导出: {} ({} 片段)", output_path, len(keep_clips))
    return output_path
