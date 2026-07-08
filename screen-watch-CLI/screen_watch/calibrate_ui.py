"""悬浮框选 / 截图框选 — 交互式标记 OCR 识别区域"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from screen_watch.capture.macos import WindowInfo
from screen_watch.config import RegionConfig, wechat_live_default
from screen_watch.utils.logger import setup_logger

logger = setup_logger()

REGION_LABELS: dict[str, str] = {
    "viewer_count": "观看人数 viewer_count",
    "chat": "弹幕区 chat",
}

REGION_COLORS: dict[str, str] = {
    "viewer_count": "#00E676",
    "chat": "#FF9100",
}

HEADER_HEIGHT = 52


@dataclass
class PickedRegion:
    name: str
    x: float
    y: float
    w: float
    h: float


def pixel_rect_to_relative(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
    height: float,
    *,
    min_size: float = 0.01,
) -> tuple[float, float, float, float] | None:
    if width <= 0 or height <= 0:
        return None
    left = min(x1, x2)
    top = min(y1, y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if w < width * min_size or h < height * min_size:
        return None
    return left / width, top / height, w / width, h / height


def regions_to_config(
    picked: dict[str, tuple[float, float, float, float]],
) -> dict[str, RegionConfig]:
    base = wechat_live_default()
    out: dict[str, RegionConfig] = {}
    for name, (x, y, w, h) in picked.items():
        default = base.regions.get(name)
        if default is None:
            default = RegionConfig(name=name)
        out[name] = RegionConfig(
            name=name,
            mode="relative",
            x=round(x, 4),
            y=round(y, 4),
            w=round(w, 4),
            h=round(h, 4),
            preprocess=list(default.preprocess),
            extract=dict(default.extract),
            diff=dict(default.diff),
            filter=dict(default.filter),
            parse=dict(default.parse),
        )
    return out


def save_annotated_screenshot(
    image_bgr,
    picked: dict[str, tuple[float, float, float, float]],
    path: str,
) -> None:
    import cv2
    from pathlib import Path

    img = image_bgr.copy()
    h, w = img.shape[:2]
    for name, (rx, ry, rw, rh) in picked.items():
        x1 = int(rx * w)
        y1 = int(ry * h)
        x2 = int((rx + rw) * w)
        y2 = int((ry + rh) * h)
        color = (0, 230, 118) if name == "viewer_count" else (0, 145, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
        cv2.putText(
            img,
            name,
            (x1 + 4, max(y1 + 22, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            cv2.LINE_AA,
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, img)


def activate_window(window: WindowInfo) -> None:
    """将目标 App 切到前台，便于用户看到即将框选的窗口"""
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{window.owner}" to activate'],
            check=False,
            capture_output=True,
        )
    except Exception as exc:
        logger.debug("activate_window 失败: %s", exc)


def _ensure_tk_display() -> None:
    if sys.platform == "darwin" and not sys.stdout.isatty():
        pass
    try:
        import tkinter as tk

        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        raise RuntimeError(
            "无法打开图形界面。请在 macOS 终端.app / iTerm 中运行 calibrate，"
            "并确保已安装 python-tk。"
        ) from exc


class RegionPickerUI:
    """Tkinter 拖拽框选（截图模式，带标题栏，居中显示）"""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        region_names: list[str],
        title: str,
        background_image=None,
        subtitle: str = "",
    ) -> None:
        self.width = width
        self.height = height
        self.region_names = region_names
        self.title = title
        self.background_image = background_image
        self.subtitle = subtitle

        self.picked: dict[str, tuple[float, float, float, float]] = {}
        self._idx = 0
        self._start_x = 0.0
        self._start_y = 0.0
        self._rect_id: int | None = None

    def run(self) -> dict[str, tuple[float, float, float, float]]:
        import tkinter as tk
        from tkinter import messagebox

        _ensure_tk_display()

        root = tk.Tk()
        root.title(self.title)
        root.configure(bg="#111111")
        root.attributes("-topmost", True)

        total_h = self.height + HEADER_HEIGHT
        root.geometry(f"{self.width}x{total_h}")
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - self.width) // 2)
        y = max(0, (sh - total_h) // 2 - 40)
        root.geometry(f"{self.width}x{total_h}+{x}+{y}")

        header = tk.Frame(root, bg="#111111", height=HEADER_HEIGHT)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        hint = tk.Label(
            header,
            text=self._hint_text(),
            fg="#FFFFFF",
            bg="#111111",
            font=("PingFang SC", 14, "bold"),
            padx=12,
            pady=6,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=max(400, self.width - 160),
        )
        hint.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(header, bg="#111111")
        btn_frame.pack(side=tk.RIGHT, padx=6)
        tk.Button(btn_frame, text="跳过", command=self._skip_current, width=6).pack(
            side=tk.LEFT, padx=2
        )
        tk.Button(btn_frame, text="完成", command=self._finish, width=6).pack(
            side=tk.LEFT, padx=2
        )
        tk.Button(btn_frame, text="取消", command=root.destroy, width=6).pack(
            side=tk.LEFT, padx=2
        )

        if self.subtitle:
            sub = tk.Label(
                root,
                text=self.subtitle,
                fg="#AAAAAA",
                bg="#222222",
                font=("PingFang SC", 11),
                anchor=tk.W,
                padx=10,
                pady=4,
            )
            sub.pack(fill=tk.X)

        canvas = tk.Canvas(
            root,
            width=self.width,
            height=self.height,
            highlightthickness=2,
            highlightbackground="#00E676",
            bg="#222222",
        )
        canvas.pack()

        if self.background_image is not None:
            canvas.create_image(0, 0, anchor=tk.NW, image=self.background_image)

        self._hint_label = hint
        self._canvas = canvas
        self._root = root

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        root.bind("<Escape>", lambda _e: root.destroy())

        root.lift()
        root.focus_force()
        root.after(100, lambda: root.attributes("-topmost", True))

        try:
            messagebox.showinfo(
                "screen-watch 框选",
                "即将在弹出窗口中框选 OCR 区域。\n\n"
                "1. 按住鼠标左键拖拽框选\n"
                "2. 先框选「观看人数」，再框选「弹幕区」\n"
                "3. 按 Esc 取消",
                parent=root,
            )
        except Exception:
            pass

        root.mainloop()
        return self.picked

    def _hint_text(self) -> str:
        if self._idx >= len(self.region_names):
            return "已完成！点击「完成」或关闭窗口"
        name = self.region_names[self._idx]
        label = REGION_LABELS.get(name, name)
        return f"步骤 {self._idx + 1}/{len(self.region_names)}：拖拽框选 【{label}】"

    def _current_name(self) -> str | None:
        if self._idx >= len(self.region_names):
            return None
        return self.region_names[self._idx]

    def _on_press(self, event) -> None:
        name = self._current_name()
        if name is None:
            return
        self._start_x = float(event.x)
        self._start_y = float(event.y)
        color = REGION_COLORS.get(name, "#FFFFFF")
        self._rect_id = self._canvas.create_rectangle(
            self._start_x,
            self._start_y,
            self._start_x,
            self._start_y,
            outline=color,
            width=3,
        )

    def _on_drag(self, event) -> None:
        if self._rect_id is None:
            return
        self._canvas.coords(self._rect_id, self._start_x, self._start_y, event.x, event.y)

    def _on_release(self, event) -> None:
        name = self._current_name()
        if name is None or self._rect_id is None:
            return
        rel = pixel_rect_to_relative(
            self._start_x,
            self._start_y,
            float(event.x),
            float(event.y),
            float(self.width),
            float(self.height),
        )
        if rel is None:
            self._canvas.delete(self._rect_id)
            self._rect_id = None
            self._hint_label.config(text="选区太小，请重新拖拽")
            return

        x, y, w, h = rel
        self.picked[name] = (x, y, w, h)
        color = REGION_COLORS.get(name, "#FFFFFF")
        self._canvas.delete(self._rect_id)
        self._canvas.create_rectangle(
            x * self.width,
            y * self.height,
            (x + w) * self.width,
            (y + h) * self.height,
            outline=color,
            width=3,
        )
        self._canvas.create_text(
            x * self.width + 6,
            y * self.height + 16,
            text=name,
            anchor=tk.NW,
            fill=color,
            font=("Menlo", 12, "bold"),
        )
        self._rect_id = None
        self._idx += 1
        self._hint_label.config(text=self._hint_text())

    def _skip_current(self) -> None:
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
            self._rect_id = None
        self._idx += 1
        self._hint_label.config(text=self._hint_text())

    def _finish(self) -> None:
        self._root.destroy()


def pick_regions_screenshot(
    image_bgr,
    region_names: list[str] | None = None,
    *,
    max_display_width: int = 1200,
    window_label: str = "",
) -> dict[str, tuple[float, float, float, float]]:
    """在窗口截图上框选（推荐，兼容性最好）"""
    from PIL import Image, ImageTk

    region_names = region_names or ["viewer_count", "chat"]
    h, w = image_bgr.shape[:2]
    scale = 1.0
    if w > max_display_width:
        scale = max_display_width / w
    disp_w = int(w * scale)
    disp_h = int(h * scale)

    rgb = image_bgr[:, :, ::-1]
    pil = Image.fromarray(rgb)
    if scale != 1.0:
        pil = pil.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(pil)

    picker = RegionPickerUI(
        width=disp_w,
        height=disp_h,
        region_names=region_names,
        title=f"screen-watch 框选区域 — {window_label or '目标窗口'}",
        background_image=photo,
        subtitle=f"窗口截图 {w}x{h} | 拖拽鼠标框选，绿色=人数 橙色=弹幕",
    )
    picker._photo_ref = photo  # prevent GC
    picked_scaled = picker.run()

    if scale == 1.0:
        return picked_scaled

    # 显示尺寸 → 原始相对坐标（scale 均匀时相对坐标不变）
    return picked_scaled


def pick_regions_overlay(
    window: WindowInfo,
    region_names: list[str] | None = None,
) -> dict[str, tuple[float, float, float, float]]:
    """overlay 模式：先截图再在同一位置打开（比纯透明悬浮层更可靠）"""
    from screen_watch.capture.macos import capture_window

    activate_window(window)
    image = capture_window(window)
    return pick_regions_screenshot(
        image,
        region_names,
        max_display_width=1400,
        window_label=window.label,
    )


def pick_regions(
    window: WindowInfo,
    *,
    mode: str = "screenshot",
    region_names: list[str] | None = None,
) -> dict[str, tuple[float, float, float, float]]:
    region_names = region_names or ["viewer_count", "chat"]
    activate_window(window)

    from screen_watch.capture.macos import capture_window

    image = capture_window(window)

    if mode == "overlay":
        logger.info("overlay 模式：使用截图弹窗框选 bounds=%s", window.bounds)
        return pick_regions_screenshot(
            image,
            region_names,
            max_display_width=1400,
            window_label=window.label,
        )

    logger.info("screenshot 模式框选 bounds=%s", window.bounds)
    return pick_regions_screenshot(
        image,
        region_names,
        window_label=window.label,
    )
