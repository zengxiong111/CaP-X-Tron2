from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from capx.integrations.tron2.target_motion import describe_target_motion


def screenshot(center):
    image = Image.new("RGB", (64, 64), (117, 101, 80))
    if center is not None:
        x, y = center
        ImageDraw.Draw(image).rectangle((x - 4, y - 4, x + 4, y + 4), fill=(220, 35, 28))
    with BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


@pytest.mark.parametrize(
    ("center", "direction", "delta"),
    [
        ((30, 22), "up", [0.0, -8.0]),
        ((30, 38), "down", [0.0, 8.0]),
        ((22, 30), "left", [-8.0, 0.0]),
        ((38, 30), "right", [8.0, 0.0]),
    ],
)
def test_red_target_motion(center, direction, delta):
    result = describe_target_motion(screenshot((30, 30)), screenshot(center))
    assert result["status"] == "moved"
    assert result["direction"] == direction
    assert result["delta_px"] == delta


def test_unchanged_or_missing_red_target():
    before = screenshot((30, 30))
    unchanged = describe_target_motion(before, screenshot((32, 30)))
    assert unchanged["status"] == "unchanged"
    assert unchanged["direction"] == "none"
    missing = describe_target_motion(before, screenshot(None))
    assert missing["status"] == "unavailable"
    assert missing["direction"] is None
    assert missing["delta_px"] is None
