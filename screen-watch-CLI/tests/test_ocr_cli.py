"""ocr CLI 测试"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Vision OCR 仅 macOS")


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    import cv2

    img = np.zeros((80, 200, 3), dtype=np.uint8)
    cv2.putText(img, "12345", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    path = tmp_path / "sample.png"
    cv2.imwrite(str(path), img)
    return path


def test_ocr_cli(sample_image: Path) -> None:
    pytest.importorskip("Vision")
    from screen_watch.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["ocr", "--input", str(sample_image), "--ocr-engine", "vision"])
    assert result.exit_code == 0, result.output
    assert "12345" in result.output or "123" in result.output
