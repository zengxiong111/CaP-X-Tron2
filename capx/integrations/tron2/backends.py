"""Shared contract for TRON2 tabletop environments."""

from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite
from random import Random
from typing import Literal, Protocol, TypedDict

import numpy as np

Arm = Literal["left", "right"]
Pose = tuple[float, float, float, float, float, float, float]


@dataclass(frozen=True)
class ActionResult:
    """Outcome of one blocking command; the code is stable across backends."""

    success: bool
    code: str = "ok"
    message: str = ""


@dataclass(frozen=True)
class TaskState:
    """Backend observations for evaluating the task after advancing the clock."""

    cube_pose: Pose
    cube_speed: float
    grasped_by: Arm | None
    open_grippers: frozenset[Arm]
    timestamp: float


class CameraFrame(TypedDict):
    """RGB, metric depth, pinhole intrinsics and the base-from-optical transform."""

    rgb: np.ndarray
    depth: np.ndarray
    K: np.ndarray
    T_base_camera: np.ndarray
    timestamp: float


class ObservationUnavailableError(RuntimeError):
    """The requested measurement is unavailable for the current configuration."""


class Tron2Backend(Protocol):
    """Blocking tabletop operations. All poses are in robot_base, with meters and wxyz."""

    def reset(self, seed: int | None = None) -> None: ...

    def get_robot_state(self) -> dict: ...

    def get_object_pose(self, name: str) -> Pose: ...

    def move_ee(self, arm: Arm, pose_base: Pose, speed: float) -> ActionResult: ...

    def open_gripper(self, arm: Arm) -> ActionResult: ...

    def close_gripper(self, arm: Arm) -> ActionResult: ...

    def get_image(self, camera_name: str) -> CameraFrame: ...

    def task_state(self) -> TaskState: ...

    def advance(self, seconds: float) -> None: ...

    def close(self) -> None: ...


class MockBackend:
    """Deterministic stand-in for testing prompts, tool feedback and task logic."""

    def __init__(self) -> None:
        self.reset()

    def reset(self, seed: int | None = None) -> None:
        rng = Random(seed)
        self._timestamp = 0.0
        self._tcp: dict[Arm, Pose] = {
            "left": (0.38, 0.19, -0.42, 1.0, 0.0, 0.0, 0.0),
            "right": (0.38, -0.19, -0.42, 1.0, 0.0, 0.0, 0.0),
        }
        self._open: set[Arm] = set(self._tcp)
        self._cube: Pose = (
            rng.uniform(0.343, 0.385), rng.uniform(-0.214, -0.178), -0.57, 1.0, 0.0, 0.0, 0.0,
        )
        self._target: Pose = (0.445, -0.111, self._cube[2], 1.0, 0.0, 0.0, 0.0)
        self._held_by: Arm | None = None
        self._cube_speed = 0.0

    def get_robot_state(self) -> dict:
        return {
            "model": "mock",
            "joint_positions": {},
            "tcp_poses": self._tcp.copy(),
            "grippers": {arm: "open" if arm in self._open else "closed" for arm in self._tcp},
            "grasp_quaternions": dict.fromkeys(self._tcp, (1.0, 0.0, 0.0, 0.0)),
            "grasped_by": self._held_by,
            "timestamp": self._timestamp,
        }

    def get_object_pose(self, name: str) -> Pose:
        if name == "cube":
            return self._cube
        if name == "target":
            return self._target
        raise ObservationUnavailableError(f"Unknown tabletop object: {name!r}")

    def move_ee(self, arm: Arm, pose_base: Pose, speed: float) -> ActionResult:
        from .safety import validate_move

        try:
            arm, pose_base, speed = validate_move(arm, pose_base, speed)
        except ValueError as exc:
            return ActionResult(False, "invalid_command", str(exc))
        x, y, z = pose_base[:3]
        if not (0.25 <= x <= 0.60 and -0.38 <= y <= 0.38 and -0.585 <= z <= -0.30):
            return ActionResult(False, "workspace", "TCP target is outside the mock tabletop workspace")
        previous = self._tcp[arm]
        duration = dist(previous[:3], pose_base[:3]) / speed
        if duration > 15.0:
            return ActionResult(False, "timeout", "Motion would exceed the mock command timeout")
        self._tcp[arm] = pose_base
        self.advance(duration)
        if self._held_by == arm:
            self._cube = (
                self._cube[0] + x - previous[0],
                self._cube[1] + y - previous[1],
                self._cube[2] + z - previous[2],
                *self._cube[3:],
            )
            self._cube_speed = speed if pose_base[:3] != previous[:3] else 0.0
        return ActionResult(True)

    def open_gripper(self, arm: Arm) -> ActionResult:
        if arm not in ("left", "right"):
            return ActionResult(False, "invalid_command", "arm must be 'left' or 'right'")
        self._open.add(arm)
        if self._held_by == arm:
            self._held_by = None
            self._cube = (self._cube[0], self._cube[1], self._target[2], *self._cube[3:])
        self.advance(0.2)
        return ActionResult(True)

    def close_gripper(self, arm: Arm) -> ActionResult:
        if arm not in ("left", "right"):
            return ActionResult(False, "invalid_command", "arm must be 'left' or 'right'")
        self._open.discard(arm)
        self.advance(0.2)
        if self._held_by is None and dist(self._cube[:3], self._tcp[arm][:3]) <= 0.025:
            self._held_by = arm
        if self._held_by != arm:
            return ActionResult(False, "empty_grasp", "Gripper closed without holding the cube")
        return ActionResult(True)

    def get_image(self, camera_name: str) -> CameraFrame:
        raise ObservationUnavailableError(f"Camera {camera_name!r} is unavailable in the mock backend")

    def task_state(self) -> TaskState:
        return TaskState(self._cube, self._cube_speed, self._held_by, frozenset(self._open), self._timestamp)

    def advance(self, seconds: float) -> None:
        if not isfinite(seconds) or seconds < 0:
            raise ValueError("seconds must be finite and nonnegative")
        self._timestamp += seconds
        self._cube_speed = 0.0

    def close(self) -> None:
        pass
