"""RGB-D center estimation for the colored markers in the TRON2 tabletop scene."""

from __future__ import annotations

import numpy as np

from .backends import CameraFrame, ObservationUnavailableError, Pose

# Crop in robot_base using the bounds of the calibrated fixed tabletop scene.
_WORKSPACE_MIN = np.array([0.20, -0.37, -0.603])
_WORKSPACE_MAX = np.array([0.66, 0.37, -0.30])
_CUBE_HALF_SIZE = 0.02
_MIN_VISIBLE_PIXELS = 20


def cube_color_mask(image: np.ndarray) -> np.ndarray:
    """Classify the red pixels used by the RGB-D cube pose tool."""
    red, green, blue = np.asarray(image, dtype=np.int16).transpose(2, 0, 1)
    return (red - green > 45) & (red - blue > 40)


def estimate_tabletop_pose(frame: CameraFrame, name: str) -> Pose:
    """Estimate the red cube or the green target's center using one calibrated frame.

    The scene uses an upright cube, with a symmetric, unmarked top. The output
    uses an identity quaternion as a convention; only the position is estimated.
    The target is reported at the desired resting center height of the cube.
    """
    rgb = np.asarray(frame["rgb"], dtype=np.int16)
    depth = np.asarray(frame["depth"])
    intrinsics = np.asarray(frame["K"])
    transform = np.asarray(frame["T_base_camera"])
    if rgb.ndim != 3 or rgb.shape[2] != 3 or depth.shape != rgb.shape[:2]:
        raise ObservationUnavailableError("The RGB and depth images must be pixel aligned")
    if intrinsics.shape != (3, 3) or transform.shape != (4, 4):
        raise ObservationUnavailableError("RGB-D camera calibration is incomplete")

    if name == "cube":
        mask = cube_color_mask(rgb)
    elif name == "target":
        red, green, blue = rgb.transpose(2, 0, 1)
        mask = (green - red > 28) & (green - blue > 28)
    else:
        raise ObservationUnavailableError(f"Unknown tabletop object: {name!r}")

    rows, columns = np.nonzero(mask & np.isfinite(depth) & (depth > 0))
    pixels = np.stack((columns, rows, np.ones_like(rows)))
    try:
        rays = np.linalg.solve(intrinsics, pixels)
    except np.linalg.LinAlgError as exc:
        raise ObservationUnavailableError("RGB-D camera intrinsics are singular") from exc
    optical_points = (rays * depth[rows, columns]).T
    base_points = optical_points @ transform[:3, :3].T + transform[:3, 3]
    in_workspace = np.all((base_points >= _WORKSPACE_MIN) & (base_points <= _WORKSPACE_MAX), axis=1)
    points = base_points[in_workspace]
    if len(points) < _MIN_VISIBLE_PIXELS:
        raise ObservationUnavailableError(f"{name!r} is not visible in the tabletop RGB-D workspace")

    if name == "cube":
        # Use the horizontal top rather than side pixels, which bias the center.
        cutoff = np.quantile(points[:, 2], 0.90) - 0.0025
        points = points[points[:, 2] >= cutoff]
        if len(points) < _MIN_VISIBLE_PIXELS:
            raise ObservationUnavailableError("Too little of the cube top is visible for a pose estimate")
    x, y, z = (float(value) for value in np.median(points, axis=0))
    center_z = z - _CUBE_HALF_SIZE if name == "cube" else z + _CUBE_HALF_SIZE
    return (x, y, center_z, 1.0, 0.0, 0.0, 0.0)
