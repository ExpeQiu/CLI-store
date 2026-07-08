"""region_to_pixels 单元测试"""

import pytest

from screen_watch.capture.macos import WindowInfo, region_to_pixels
from screen_watch.config import RegionConfig


@pytest.fixture
def window() -> WindowInfo:
    return WindowInfo(title="直播", owner="微信", bounds=(100, 200, 800, 600))


def test_relative_region_pixels(window: WindowInfo) -> None:
    region = RegionConfig(name="viewer_count", mode="relative", x=0.1, y=0.2, w=0.3, h=0.1)
    px = region_to_pixels(window, region, scale=2.0)
    assert px == {"left": 360, "top": 640, "width": 480, "height": 120}


def test_absolute_region_pixels(window: WindowInfo) -> None:
    region = RegionConfig(name="chat", mode="absolute", x=10, y=20, w=100, h=50)
    px = region_to_pixels(window, region, scale=1.0)
    assert px == {"left": 10, "top": 20, "width": 100, "height": 50}
