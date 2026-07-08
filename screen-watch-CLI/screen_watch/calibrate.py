"""区域校准"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from screen_watch.calibrate_ui import (
    pick_regions,
    regions_to_config,
    save_annotated_screenshot,
)
from screen_watch.capture import capture_window, list_windows, save_window_screenshot
from screen_watch.config import AppConfig, RegionConfig, wechat_live_default
from screen_watch.config_io import save_config
from screen_watch.utils.logger import setup_logger

logger = setup_logger()


def run_calibrate(
    *,
    preset: str,
    window_title: str,
    save_config_path: str | None,
    use_defaults: bool,
    use_pick: bool = True,
    pick_mode: str = "screenshot",
    region_names: list[str] | None = None,
    window_index: int | None = None,
) -> AppConfig:
    windows = list_windows(window_title)
    if not windows:
        raise RuntimeError(f"未找到匹配窗口: {window_title}")

    if window_index is not None:
        if window_index < 0 or window_index >= len(windows):
            raise RuntimeError(f"window-index 无效: {window_index}，共 {len(windows)} 个窗口")
        window = windows[window_index]
    else:
        window = windows[0]
    if len(windows) > 1:
        click.echo(f"匹配到 {len(windows)} 个窗口:", err=True)
        for i, w in enumerate(windows):
            click.echo(f"  [{i}] {w.label}\t{w.bounds}", err=True)
        click.echo("使用最大窗口。若不对，请用 --window-index 指定。", err=True)

    region_names = region_names or ["viewer_count", "chat"]

    if use_pick and not use_defaults:
        click.echo(
            "\n>>> 即将弹出【框选窗口】，请在截图上拖拽鼠标框选区域。"
            "若未看到窗口，请检查 Dock 或按 Cmd+Tab 切换。\n",
            err=True,
        )
        picked = pick_regions(window, mode=pick_mode, region_names=region_names)
        if not picked:
            raise RuntimeError("未框选任何区域，请重试或使用 --defaults")

        out_dir = Path("logs/calibrate")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot = out_dir / f"{preset}_{ts}.png"
        save_window_screenshot(window, str(screenshot))
        click.echo(f"已保存窗口截图: {screenshot}", err=True)
        click.echo(f"窗口: {window.label} bounds={window.bounds}", err=True)

        annotated = out_dir / f"{preset}_{ts}_regions.png"
        try:
            image = capture_window(window)
            save_annotated_screenshot(image, picked, str(annotated))
            click.echo(f"已保存标注图: {annotated}", err=True)
        except Exception as exc:
            logger.warning("保存标注图失败: %s", exc)

        regions = regions_to_config(picked)
        base = wechat_live_default()
        config = AppConfig(
            preset=preset,
            window_title=window_title,
            interval_sec=base.interval_sec,
            regions=regions,
        )
        for name, coords in picked.items():
            click.echo(
                f"  {name}: x={coords[0]:.3f} y={coords[1]:.3f} "
                f"w={coords[2]:.3f} h={coords[3]:.3f}",
                err=True,
            )
    elif use_defaults:
        config = wechat_live_default()
        config.preset = preset
        config.window_title = window_title
    else:
        config = _prompt_regions(preset, window_title)

    if save_config_path:
        path = save_config(config, save_config_path)
        click.echo(f"已写入配置: {path}", err=True)

    click.echo(
        "\n下一步: screen-watch capture once --region viewer_count --window "
        f"\"{window_title}\" --config {save_config_path or 'config.yaml'} -v",
        err=True,
    )
    return config


def _prompt_region(name: str, default: RegionConfig) -> RegionConfig:
    click.echo(f"\n--- 区域: {name} (相对坐标 0~1) ---")
    x = click.prompt("x", type=float, default=default.x)
    y = click.prompt("y", type=float, default=default.y)
    w = click.prompt("w", type=float, default=default.w)
    h = click.prompt("h", type=float, default=default.h)
    return RegionConfig(
        name=name,
        mode="relative",
        x=x,
        y=y,
        w=w,
        h=h,
        preprocess=list(default.preprocess),
        extract=dict(default.extract),
        diff=dict(default.diff),
        filter=dict(default.filter),
        parse=dict(default.parse),
    )


def _prompt_regions(preset: str, window_title: str) -> AppConfig:
    base = wechat_live_default()
    regions: dict[str, RegionConfig] = {}
    for name in ("viewer_count", "chat"):
        default = base.regions[name]
        regions[name] = _prompt_region(name, default)
    return AppConfig(
        preset=preset,
        window_title=window_title,
        interval_sec=base.interval_sec,
        regions=regions,
    )
