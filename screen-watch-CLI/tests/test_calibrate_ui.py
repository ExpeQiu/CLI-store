"""pixel_rect_to_relative 单元测试"""

from screen_watch.calibrate_ui import pixel_rect_to_relative


def test_pixel_rect_to_relative():
    r = pixel_rect_to_relative(10, 20, 110, 70, 1000, 800)
    assert r is not None
    x, y, w, h = r
    assert abs(x - 0.01) < 1e-6
    assert abs(y - 0.025) < 1e-6
    assert abs(w - 0.1) < 1e-6
    assert abs(h - 0.0625) < 1e-6


def test_too_small_returns_none():
    assert pixel_rect_to_relative(0, 0, 2, 2, 1000, 800) is None
