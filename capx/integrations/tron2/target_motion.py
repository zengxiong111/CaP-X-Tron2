"""Image-only red-cube motion VDM for fixed head-camera RGB screenshots."""

from io import BytesIO

import numpy as np
from PIL import Image, UnidentifiedImageError

MOTION_THRESHOLD_PX = 3.0
MIN_RED_PIXELS = 12


def _rgb(data: bytes) -> np.ndarray:
    """Decode screenshot bytes as an RGB array."""
    with Image.open(BytesIO(data)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.int16)


def _center(image: np.ndarray) -> np.ndarray | None:
    """Find the robust centroid of saturated red pixels."""
    red = image[..., 0]
    green = image[..., 1]
    blue = image[..., 2]
    mask = (red > 100) & (red > green * 1.35) & (red > blue * 1.25) & ((red - green) > 35)
    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_RED_PIXELS:
        return None

    points = np.column_stack((xs, ys)).astype(float)
    median = np.median(points, axis=0)
    distances = np.linalg.norm(points - median, axis=1)
    radius = max(float(np.percentile(distances, 90)), 1.0)
    return np.mean(points[distances <= radius], axis=0)


def _unavailable(reason: str) -> dict:
    return {
        "text": f"Target motion unavailable: {reason}.",
        "status": "unavailable",
        "delta_px": None,
        "direction": None,
    }


def describe_target_motion(before: bytes, after: bytes) -> dict:
    """Describe red-target image-plane motion and return pixel displacement."""
    try:
        first = _rgb(before)
        second = _rgb(after)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return _unavailable(f"an image could not be decoded ({exc})")

    if first.shape != second.shape:
        return _unavailable("image dimensions differ")

    first_center = _center(first)
    second_center = _center(second)
    if first_center is None or second_center is None:
        return _unavailable("red target is missing or occluded in at least one image")

    dx, dy = second_center - first_center
    magnitude = float(np.hypot(dx, dy))
    delta = [round(float(dx), 2), round(float(dy), 2)]
    if magnitude < MOTION_THRESHOLD_PX:
        return {
            "text": "The red target appears unchanged in the image.",
            "status": "unchanged",
            "delta_px": delta,
            "direction": "none",
        }

    if abs(dy) >= abs(dx):
        direction = "down" if dy > 0 else "up"
    else:
        direction = "right" if dx > 0 else "left"

    return {
        "text": (
            f"The red target moved {direction} in the image "
            f"({dx:+.1f}, {dy:+.1f} px; {magnitude:.1f} px total)."
        ),
        "status": "moved",
        "delta_px": delta,
        "direction": direction,
    }
