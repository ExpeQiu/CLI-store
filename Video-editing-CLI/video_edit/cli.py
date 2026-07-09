"""video-edit CLI 入口。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from video_edit.__version__ import __version__
from video_edit.config import init_config_file, load_config
from video_edit.pipelines.aroll import (
    run_align_only,
    run_aroll_pipeline,
    run_export_only,
)
from video_edit.services.batch_queue import run_batch
from video_edit.services.multicam import save_sync_map, sync_multicam
from video_edit.services.audio import extract_audio, probe_duration, require_ffmpeg
from video_edit.services.transcribe import save_transcript, transcribe_audio
from video_edit.utils.errors import DependencyError, VideoEditError
from video_edit.utils.logger import EXIT_ERROR, EXIT_OK, setup_logger


def _version_callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"video-edit {__version__}")
    ctx.exit(EXIT_OK)


def _emit_result(data: dict, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


@click.group()
@click.option("--version", is_flag=True, callback=_version_callback, expose_value=False, is_eager=True)
@click.option("-v", "--verbose", is_flag=True, help="DEBUG 日志")
@click.option("-q", "--quiet", is_flag=True, help="仅 WARNING 及以上")
@click.option("--config", "config_path", type=click.Path(), default=None, help="配置文件路径")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool, config_path: str | None) -> None:
    """AI 辅助 A-Roll 口播初剪 — 输出 FCPXML 时间轴"""
    setup_logger(verbose=verbose, quiet=quiet)
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@cli.group()
def aroll() -> None:
    """A-Roll 初剪子命令"""


@aroll.command("run")
@click.option("--video", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--script", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs"))
@click.option("--demo", is_flag=True, help="Mock 数据验收，无需视频/Whisper")
@click.option(
    "--stop-at",
    type=click.Choice(["extract", "transcribe", "align", "refine", "export"]),
    default=None,
    help="停在指定阶段",
)
@click.option("--resume", is_flag=True, help="从 work_dir/checkpoint.json 断点续跑")
@click.option(
    "--multicam",
    "multicam_paths",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="附加机位视频（可多次指定）",
)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def aroll_run(
    ctx: click.Context,
    video: Path | None,
    script: Path | None,
    output: Path,
    demo: bool,
    stop_at: str | None,
    resume: bool,
    multicam_paths: tuple[Path, ...],
    fmt: str,
) -> None:
    """完整 A-Roll 初剪流水线"""
    config = ctx.obj["config"]
    work_dir = None
    if resume and not demo:
        if not output.exists():
            click.echo("错误: --resume 需指定已有 job 目录作为 --output", err=True)
            sys.exit(EXIT_ERROR)
        work_dir = output
    try:
        result = run_aroll_pipeline(
            video=video,
            script=script,
            output_dir=output if not work_dir else output.parent,
            config=config,
            demo=demo,
            stop_at=stop_at,
            secondary_videos=list(multicam_paths) if multicam_paths else None,
            resume=resume,
            work_dir=work_dir,
        )
    except (VideoEditError, ValueError, FileNotFoundError) as exc:
        click.echo(f"错误: {exc}", err=True)
        sys.exit(EXIT_ERROR)

    payload = {
        "job_id": result.job_id,
        "output_dir": str(result.output_dir),
        "transcript": str(result.transcript_path) if result.transcript_path else None,
        "decisions": str(result.decisions_path) if result.decisions_path else None,
        "fcpxml": str(result.fcpxml_path) if result.fcpxml_path else None,
        "edl": str(result.edl_path) if result.edl_path else None,
        "srt": str(result.srt_path) if result.srt_path else None,
        "sync_map": str(result.sync_map_path) if result.sync_map_path else None,
        "exports": {k: str(v) for k, v in result.exports.items()},
        **result.summary,
    }
    _emit_result(payload, fmt)


@aroll.command("transcribe")
@click.option("--video", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs/transcript.json"))
@click.pass_context
def aroll_transcribe(ctx: click.Context, video: Path, output: Path) -> None:
    """仅转录：视频 → transcript.json"""
    config = ctx.obj["config"]
    try:
        require_ffmpeg()
        audio_path = output.parent / "audio.wav"
        extract_audio(video, audio_path)
        transcript = transcribe_audio(audio_path, config=config.transcribe, source_label=str(video))
        if transcript.duration_sec <= 0:
            transcript.duration_sec = probe_duration(video)
        save_transcript(transcript, output)
        click.echo(json.dumps({"transcript": str(output), "words": len(transcript.words)}, ensure_ascii=False))
    except (DependencyError, VideoEditError, RuntimeError) as exc:
        click.echo(f"错误: {exc}", err=True)
        sys.exit(EXIT_ERROR)


@aroll.command("align")
@click.option("--transcript", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--script", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs/edit_decisions.json"))
@click.pass_context
def aroll_align(ctx: click.Context, transcript: Path, script: Path, output: Path) -> None:
    """脚本对齐 → edit_decisions.json"""
    config = ctx.obj["config"]
    decision = run_align_only(transcript, script, output, config)
    click.echo(
        json.dumps(
            {
                "decisions": str(output),
                "kept_clips": decision.stats.kept_clips,
                "retain_ratio": decision.retain_ratio,
            },
            ensure_ascii=False,
        )
    )


@aroll.command("export")
@click.option("--decisions", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--video", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs"))
@click.pass_context
def aroll_export(ctx: click.Context, decisions: Path, video: Path, output: Path) -> None:
    """剪辑决策 → FCPXML"""
    config = ctx.obj["config"]
    result = run_export_only(decisions, video, output, config)
    click.echo(json.dumps({"fcpxml": str(result.fcpxml_path), "edl": str(result.edl_path), "exports": {k: str(v) for k, v in result.exports.items()}}, ensure_ascii=False))


@cli.group()
def multicam() -> None:
    """多机位同步"""


@multicam.command("sync")
@click.option("--primary", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--secondary",
    "secondaries",
    multiple=True,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs/sync_map.json"))
@click.pass_context
def multicam_sync(
    ctx: click.Context,
    primary: Path,
    secondaries: tuple[Path, ...],
    output: Path,
) -> None:
    """波形互相关同步多机位，输出 sync_map.json"""
    config = ctx.obj["config"]
    sync_map = sync_multicam(
        primary,
        list(secondaries),
        sample_rate=config.multicam.sample_rate,
        max_lag_sec=config.multicam.max_lag_sec,
    )
    save_sync_map(sync_map, output)
    click.echo(json.dumps(sync_map.to_dict(), ensure_ascii=False, indent=2))


@cli.group()
def batch() -> None:
    """批量任务队列"""


@batch.command("run")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("outputs"))
@click.option("--resume", is_flag=True, help="跳过已完成任务并断点续跑")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def batch_run(ctx: click.Context, manifest: Path, output: Path, resume: bool, fmt: str) -> None:
    """从 manifest.json 批量执行 A-Roll 初剪"""
    config = ctx.obj["config"]
    summary = run_batch(manifest, output, config, resume=resume)
    _emit_result(summary, fmt)


@batch.command("init")
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("batch_manifest.example.json"))
def batch_init(output: Path) -> None:
    """生成批量任务 manifest 模板"""
    example = {
        "jobs": [
            {"id": "ep01", "video": "/path/to/ep01_aroll.mp4", "script": "/path/to/ep01.txt"},
            {"id": "ep02", "video": "/path/to/ep02_aroll.mp4", "script": "/path/to/ep02.txt"},
        ]
    }
    output.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"已创建: {output}")


@cli.group()
def config_cmd() -> None:
    """配置管理"""


@config_cmd.command("init")
@click.option("-o", "--output", type=click.Path(path_type=Path), default=Path("config.yaml"))
@click.option("--force", is_flag=True)
def config_init(output: Path, force: bool) -> None:
    """生成 config.yaml"""
    try:
        path = init_config_file(output, force=force)
        click.echo(f"已创建: {path}")
    except FileExistsError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_ERROR)


@cli.command("health")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def health(fmt: str) -> None:
    """检测 ffmpeg / whisper 依赖"""
    status: dict[str, str] = {}
    try:
        require_ffmpeg()
        status["ffmpeg"] = "ok"
    except DependencyError as exc:
        status["ffmpeg"] = str(exc)

    try:
        import httpx  # noqa: F401

        status["httpx"] = "ok"
    except ImportError:
        status["httpx"] = "missing"

    try:
        import faster_whisper  # noqa: F401

        status["faster_whisper"] = "ok"
    except ImportError:
        status["faster_whisper"] = "missing (pip install -e '.[whisper]')"

    try:
        import whisperx  # noqa: F401

        status["whisperx"] = "ok"
    except ImportError:
        status["whisperx"] = "missing (pip install -e '.[whisperx]')"

    if fmt == "json":
        click.echo(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        for k, v in status.items():
            click.echo(f"{k}: {v}")


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
