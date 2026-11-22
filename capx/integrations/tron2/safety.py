"""Validate the public command format before passing it to a motion backend."""

from __future__ import annotations

from collections.abc import Iterable
from math import hypot, isclose, isfinite
from numbers import Real
from typing import cast

from .backends import Arm, Pose

MAX_SPEED_M_S = 0.2


def validate_arm(arm: object) -> Arm:
    if not isinstance(arm, str) or arm not in ("left", "right"):
        raise ValueError("arm must be 'left' or 'right'")
    return cast(Arm, arm)


def validate_move(arm: object, pose_base: Iterable[float], speed: float) -> tuple[Arm, Pose, float]:
    arm_name = validate_arm(arm)
    if not isinstance(speed, Real) or isinstance(speed, bool) or not 0 < speed <= MAX_SPEED_M_S:
        raise ValueError(f"speed must be in (0, {MAX_SPEED_M_S}] m/s")
    try:
        pose = tuple(pose_base)
    except TypeError as exc:
        raise ValueError("pose_base must contain [x, y, z, qw, qx, qy, qz]") from exc
    if len(pose) != 7 or any(
        not isinstance(value, Real) or isinstance(value, bool) or not isfinite(value) for value in pose
    ):
        raise ValueError("pose_base must contain seven finite numbers [x, y, z, qw, qx, qy, qz]")
    norm = hypot(*pose[3:])
    if not isclose(norm, 1.0, rel_tol=1e-3):
        raise ValueError("pose_base requires a unit quaternion in wxyz order")
    position = tuple(float(value) for value in pose[:3])
    quaternion = tuple(float(value) / norm for value in pose[3:])
    return arm_name, cast(Pose, position + quaternion), float(speed)
