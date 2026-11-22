"""High-level tools exposed to the CaP-X coding agent in TRON2 simulation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from capx.envs.base import BaseEnv
from capx.integrations.base_api import ApiBase

from .backends import ActionResult, Arm, CameraFrame, Pose

if TYPE_CHECKING:
    from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv


class Tron2ControlApi(ApiBase):
    """Expose the same six tabletop operations for the supported simulation backends."""

    _env: Tron2MujocoEnv

    def __init__(self, env: BaseEnv) -> None:
        from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv

        if not isinstance(env, Tron2MujocoEnv):
            raise TypeError("Tron2ControlApi requires a Tron2MujocoEnv")
        super().__init__(env)

    def functions(self) -> dict[str, Callable[..., Any]]:
        return {
            "get_robot_state": self.get_robot_state,
            "get_object_pose": self.get_object_pose,
            "move_ee": self.move_ee,
            "open_gripper": self.open_gripper,
            "close_gripper": self.close_gripper,
            "get_image": self.get_image,
        }

    def get_robot_state(self) -> dict[str, Any]:
        """Read the current joint, TCP, gripper and contact observations.

        Returns:
            Dictionary with `tcp_poses` and `grippers` keyed by `left` and `right`,
            `joint_positions` (joint units from the backend), `grasp_quaternions`
            (model-specific top-down wxyz orientation per arm), `grasped_by`
            (arm currently holding the cube, or None), and simulation `timestamp`
            in seconds. TCP poses use [x, y, z, qw, qx, qy, qz] in robot_base.
        """
        return self._env.get_robot_state()

    def get_object_pose(self, name: str) -> Pose:
        """Read the cube or target center pose in the configured simulation profile.

        S1 reads simulation truth. S2 estimates the center from RGB-D and uses
        the identity quaternion for the upright tabletop object convention.

        Args:
            name: `cube` or `target`.

        Returns:
            [x, y, z, qw, qx, qy, qz] in robot_base, position in meters.

        Raises:
            ObservationUnavailableError: No pose is available for the name or camera view.
        """
        return self._env.get_object_pose(name)

    def move_ee(self, arm: Arm, pose_base: Sequence[float], speed: float = 0.1) -> dict[str, Any]:
        """Move one TCP to a target pose and wait for the backend result.

        Args:
            arm: `left` or `right`.
            pose_base: [x, y, z, qw, qx, qy, qz] in robot_base; meters and a unit wxyz quaternion.
            speed: Requested max TCP speed in m/s, in (0, 0.2].

        Returns:
            Dictionary with `success`, `code` and `message`. Check success before continuing.
        """
        return self._log_outcome("move_ee", arm, self._env.move_ee(arm, pose_base, speed))

    def open_gripper(self, arm: Arm) -> dict[str, Any]:
        """Open the gripper on `left` or `right` and wait for feedback.

        Returns:
            Dictionary with `success`, `code` and `message`.
        """
        return self._log_outcome("open_gripper", arm, self._env.open_gripper(arm))

    def close_gripper(self, arm: Arm) -> dict[str, Any]:
        """Close the gripper on `left` or `right` and wait for feedback.

        Returns:
            Dictionary with `success`, `code` and `message`. Verify `grasped_by`
            and the cube pose before relying on a hold.
        """
        return self._log_outcome("close_gripper", arm, self._env.close_gripper(arm))

    def get_image(self, camera_name: str) -> CameraFrame:
        """Read RGB-D from `head`, `overview`, `left_wrist` or `right_wrist`.

        Returns:
            `rgb` (H, W, 3) uint8, `depth` (H, W) meters, `K` (3, 3) pinhole
            intrinsics, `T_base_camera` (4, 4) base-from-optical transform, and
            a `timestamp` in seconds in the same clock as robot state.

        Raises:
            ObservationUnavailableError: The camera or rendering is unavailable.
        """
        return self._env.get_image(camera_name)

    def _log_outcome(self, tool: str, arm: Arm, result: ActionResult) -> dict[str, Any]:
        status = result.code if not result.message else f"{result.code}: {result.message}"
        self._log_step(tool, f"{arm}: {status}")
        return asdict(result)
