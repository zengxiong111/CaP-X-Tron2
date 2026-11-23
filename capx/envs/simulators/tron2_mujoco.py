"""CaP-X environment for TRON2 tabletop tasks in simulation."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from math import hypot, isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from gymnasium import Env
from gymnasium.error import ResetNeeded

from capx.envs.base import BaseEnv

if TYPE_CHECKING:
    from capx.integrations.tron2.backends import (
        ActionResult,
        Arm,
        CameraFrame,
        Pose,
        TaskState,
        Tron2Backend,
    )


Tron2Task = Literal["cube_lift", "pick_place"]
_CAMERA_NAME = "head"
_STABILITY_SECONDS = 0.25
_SAMPLE_SECONDS = 0.05
_SETTLE_STEPS = 7
_TIME_TOLERANCE = 1e-8
_MAX_STABLE_SPEED = 0.04  # m/s
_LIFT_HEIGHT = 0.07  # m above the initial cube center
_TARGET_RADIUS = 0.035  # m from the target center in the table plane
_TARGET_Z_TOLERANCE = 0.012  # m along the vertical axis


class Tron2MujocoEnv(BaseEnv):
    """Run a tabletop task with the MuJoCo backend or a deterministic test double.

    ``max_steps`` counts motion and gripper commands, including rejected requests.
    ``max_seconds`` is elapsed backend time. ``max_attempts`` counts code turns.
    After each turn the environment samples cube stability for up to 0.35 s.
    Set ``visual_pose`` to estimate poses from RGB-D in S2 MuJoCo trials.
    """

    def __init__(
        self,
        *,
        task: Tron2Task = "cube_lift",
        backend: Literal["mujoco", "mock"] | Tron2Backend = "mujoco",
        model_path: str | Path | None = None,
        max_steps: int = 48,
        max_seconds: float = 90.0,
        max_attempts: int = 6,
        privileged: bool = False,
        enable_render: bool = False,
        visual_pose: bool = False,
        perception_url: str | None = None,
        perception_timeout_s: float = 5.0,
        viser_debug: bool = False,
    ) -> None:
        super().__init__()
        if task not in ("cube_lift", "pick_place"):
            raise ValueError(f"Unknown TRON2 task: {task!r}")
        if type(max_steps) is not int or max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if type(max_attempts) is not int or max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        if not isfinite(max_seconds) or max_seconds <= 0:
            raise ValueError("max_seconds must be positive and finite")
        if not isfinite(perception_timeout_s) or perception_timeout_s <= 0:
            raise ValueError("perception_timeout_s must be positive and finite")
        if viser_debug:
            raise ValueError("TRON2 does not support viser_debug")
        if visual_pose:
            from capx.integrations.tron2.mujoco_backend import MujocoBackend

            if privileged or not enable_render or not (
                backend == "mujoco" or isinstance(backend, MujocoBackend)
            ):
                raise ValueError(
                    "visual_pose requires a MuJoCo backend, privileged=False and enable_render=True"
                )

        self.task = task
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.max_attempts = max_attempts
        self.privileged = privileged
        self.enable_render = enable_render
        self.visual_pose = visual_pose
        self.perception_url = perception_url
        self.perception_timeout_s = perception_timeout_s

        if isinstance(backend, str):
            if backend == "mujoco":
                from capx.integrations.tron2.mujoco_backend import MujocoBackend

                backend = MujocoBackend(model_path=model_path, enable_render=enable_render)
            elif backend == "mock" and model_path is None:
                from capx.integrations.tron2.backends import MockBackend

                backend = MockBackend()
            else:
                raise ValueError("Choose backend='mujoco' or backend='mock' without model_path")
        elif model_path is not None:
            raise ValueError("model_path only applies when backend='mujoco'")

        self._backend = backend
        self._initial_state: TaskState | None = None
        self._target_pose: Pose | None = None
        self._sim_step_count = 0
        self.pose_estimate_calls = 0
        self._attempts = 0
        self._attempt_start = 0
        self._previous_attempt_start = 0
        self._completed = False
        self._truncated = False
        self._holding_arm: Arm | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=24)

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Reset physics, task progress and trace; explicit seeds reproduce placement."""
        Env.reset(self, seed=seed)
        self._backend.reset(seed)
        self._initial_state = self._backend.task_state()
        self._target_pose = (
            self._backend.get_object_pose("target") if self.task == "pick_place" else None
        )
        self._sim_step_count = 0
        self.pose_estimate_calls = 0
        self._attempts = 0
        self._attempt_start = 0
        self._previous_attempt_start = 0
        self._completed = False
        self._truncated = False
        self._holding_arm = None
        self._history.clear()
        observation = self.get_observation()
        return observation, observation["tron2_episode"].copy()

    def step(
        self, action: Mapping[str, Any]
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        """Execute one named command; CaP-X normally runs several commands per code turn."""
        if not isinstance(action, Mapping):
            raise TypeError("TRON2 step expects a command dictionary")
        command = action.get("action")
        if not isinstance(command, str):
            raise ValueError("action must be move_ee, open_gripper or close_gripper")
        if command == "move_ee":
            outcome = self.move_ee(
                action.get("arm"), action.get("pose_base"), action.get("speed", 0.1)
            )
        elif command == "open_gripper":
            outcome = self.open_gripper(action.get("arm"))
        elif command == "close_gripper":
            outcome = self.close_gripper(action.get("arm"))
        else:
            raise ValueError("action must be move_ee, open_gripper or close_gripper")

        self._settle_and_check_limits()
        observation = self.get_observation()
        info = observation["tron2_episode"].copy()
        info["action_result"] = asdict(outcome)
        return (
            observation,
            self.compute_reward(),
            self.task_completed(),
            info["episode_truncated"],
            info,
        )

    def get_robot_state(self) -> dict[str, Any]:
        self._require_reset()
        return deepcopy(self._backend.get_robot_state())

    def get_object_pose(self, name: str) -> Pose:
        from capx.integrations.tron2.backends import ObservationUnavailableError

        self._require_reset()
        if self.privileged:
            return self._backend.get_object_pose(name)
        if not self.visual_pose:
            raise ObservationUnavailableError("Object poses require an S1 or S2 simulation profile")

        if name not in ("cube", "target"):
            raise ObservationUnavailableError(f"Unknown tabletop object: {name!r}")
        try:
            return self._estimate_pose(self.get_image(_CAMERA_NAME), name)
        except ObservationUnavailableError as head_error:
            try:
                return self._estimate_pose(self.get_image("overview"), name)
            except ObservationUnavailableError as overview_error:
                raise ObservationUnavailableError(
                    f"Cannot estimate {name!r} from head ({head_error}) or overview ({overview_error})"
                ) from overview_error

    def _estimate_pose(self, frame: CameraFrame, name: str) -> Pose:
        from capx.integrations.tron2.perception import WORKSPACE_Z_OFFSET, estimate_tabletop_pose

        self.pose_estimate_calls += 1
        if self.perception_url:
            from capx.integrations.tron2.perception_service import request_pose

            return request_pose(
                self.perception_url, frame, name, workspace_z_offset=WORKSPACE_Z_OFFSET,
                timeout=self.perception_timeout_s,
            )
        return estimate_tabletop_pose(
            frame, name, workspace_z_offset=WORKSPACE_Z_OFFSET
        )

    def get_image(self, camera_name: str) -> CameraFrame:
        self._require_reset()
        return self._backend.get_image(camera_name)

    def move_ee(self, arm: Arm, pose_base: Sequence[float], speed: float = 0.1) -> ActionResult:
        return self._execute_command("move_ee", arm, pose_base, speed)

    def open_gripper(self, arm: Arm) -> ActionResult:
        return self._execute_command("open_gripper", arm)

    def close_gripper(self, arm: Arm) -> ActionResult:
        return self._execute_command("close_gripper", arm)

    def get_observation(self) -> dict[str, Any]:
        """Return robot state, recent feedback and optional S1 poses and RGB-D."""
        from capx.integrations.tron2.backends import ObservationUnavailableError

        observation = {
            "robot_state": self.get_robot_state(),
            "tron2_episode": self.episode_info(),
        }
        if self.privileged:
            observation["object_poses"] = {
                name: self.get_object_pose(name) for name in ("cube", "target")
            }
        if self.enable_render:
            try:
                camera = self.get_image(_CAMERA_NAME)
            except ObservationUnavailableError:
                pass
            else:
                depth = np.asarray(camera["depth"], dtype=np.float32)
                if depth.ndim == 2:
                    depth = depth[..., np.newaxis]
                observation["robot0_robotview"] = {
                    "images": {"rgb": camera["rgb"], "depth": depth},
                    "intrinsics": camera["K"],
                    "pose_mat": camera["T_base_camera"],
                    "timestamp": camera["timestamp"],
                }
        return observation

    def compute_reward(self) -> float:
        return float(self.task_completed())

    def task_completed(self) -> bool:
        return self._completed

    def finish_attempt(self) -> None:
        """Evaluate the task and consume one code turn."""
        self._require_reset()
        if self._completed or self._truncated:
            return
        self._attempts += 1
        self._previous_attempt_start = self._attempt_start
        self._attempt_start = self._sim_step_count
        self._settle_and_check_limits()

    def _settle_and_check_limits(self) -> None:
        if self._completed or self._truncated:
            return
        self._sample_goal()
        self._truncated = self._budget_failure(self._backend.task_state()) is not None

    def _sample_goal(self) -> None:
        """Sample a consecutive dwell window after a group of commands."""
        initial = self._require_reset()
        deadline = initial.timestamp + self.max_seconds
        stable_since = None
        for tick in range(_SETTLE_STEPS + 1):
            state = self._backend.task_state()
            if state.timestamp > deadline + _TIME_TOLERANCE:
                return
            if self._within_goal(state):
                if stable_since is None:
                    stable_since = state.timestamp
                if state.timestamp - stable_since >= _STABILITY_SECONDS - _TIME_TOLERANCE:
                    self._completed = True
                    return
            else:
                stable_since = None
            if (
                tick == _SETTLE_STEPS
                or state.timestamp + _SAMPLE_SECONDS > deadline + _TIME_TOLERANCE
            ):
                return
            self._backend.advance(_SAMPLE_SECONDS)

    def episode_info(self) -> dict[str, Any]:
        initial = self._require_reset()
        state = self._backend.task_state()
        budget_failure = self._budget_failure(state)
        history = [entry.copy() for entry in self._history]
        failure = budget_failure
        if failure is None and not self._completed and self._attempts:
            last_failure = next(
                (
                    entry
                    for entry in reversed(history)
                    if self._previous_attempt_start < entry["step"] <= self._attempt_start
                    and not entry["success"]
                ),
                None,
            )
            if last_failure is None:
                failure = {
                    "code": "goal_not_met",
                    "message": "Cube did not meet the task's hold or placement criteria",
                }
            else:
                failure = {key: last_failure[key] for key in ("code", "message")}
        return {
            "task_completed": self._completed,
            "episode_timed_out": budget_failure is not None
            and budget_failure["code"] == "episode_time_limit",
            "episode_truncated": budget_failure is not None,
            "failure_reason": failure,
            "last_action": history[-1].copy() if history else None,
            "action_history": history,
            "steps": self._sim_step_count,
            "attempts": self._attempts,
            "elapsed_seconds": state.timestamp - initial.timestamp,
        }

    def render(self, mode: str = "rgb_array") -> np.ndarray | None:
        if mode != "rgb_array":
            raise ValueError("TRON2 render only supports rgb_array")
        return self._render_rgb(_CAMERA_NAME)

    def render_wrist(self) -> np.ndarray | None:
        return self._render_rgb("right_wrist")

    def _render_rgb(self, camera_name: str) -> np.ndarray | None:
        from capx.integrations.tron2.backends import ObservationUnavailableError

        try:
            return self.get_image(camera_name)["rgb"]
        except ObservationUnavailableError:
            return None

    def enable_video_capture(self, enabled: bool = True, *, clear: bool = True) -> None:
        if enabled:
            raise NotImplementedError(
                "TRON2 provides RGB-D snapshots; motion video capture is unavailable"
            )

    def get_video_frames(self, *, clear: bool = False) -> list[np.ndarray]:
        return []

    def close(self) -> None:
        self._backend.close()
        self._initial_state = None

    def _require_reset(self) -> TaskState:
        if self._initial_state is None:
            raise ResetNeeded("Reset the TRON2 environment before using it")
        return self._initial_state

    def _budget_failure(self, state: TaskState) -> dict[str, str] | None:
        if self._completed:
            return None
        start = self._require_reset().timestamp
        # The dwell sampler cannot make further progress when less than one tick remains.
        if state.timestamp - start + _SAMPLE_SECONDS > self.max_seconds + _TIME_TOLERANCE:
            return {"code": "episode_time_limit", "message": "Simulation time limit reached"}
        if self._sim_step_count >= self.max_steps:
            return {"code": "command_limit", "message": "Motion and gripper command limit reached"}
        if self._attempts >= self.max_attempts:
            return {"code": "attempt_limit", "message": "Code turn limit reached"}
        return None

    def _within_goal(self, state: TaskState) -> bool:
        if not 0 <= state.cube_speed <= _MAX_STABLE_SPEED:
            return False
        if self.task == "cube_lift":
            initial_z = self._require_reset().cube_pose[2]
            return state.grasped_by is not None and state.cube_pose[2] - initial_z >= _LIFT_HEIGHT

        target = self._target_pose
        if target is None:
            return False
        x, y, z = state.cube_pose[:3]
        return (
            state.grasped_by is None
            and self._holding_arm in state.open_grippers
            and hypot(x - target[0], y - target[1]) <= _TARGET_RADIUS
            and abs(z - target[2]) <= _TARGET_Z_TOLERANCE
        )

    def _execute_command(
        self,
        command: Literal["move_ee", "open_gripper", "close_gripper"],
        arm: Arm,
        pose_base: Sequence[float] | None = None,
        speed: float = 0.1,
    ) -> ActionResult:
        from capx.integrations.tron2.backends import ActionResult
        from capx.integrations.tron2.safety import validate_arm, validate_move

        self._require_reset()
        if self._completed:
            return ActionResult(False, "episode_complete", "The task has already succeeded")
        before = self._backend.task_state()
        budget_failure = self._budget_failure(before)
        if budget_failure is not None:
            return ActionResult(False, **budget_failure)

        try:
            checked_arm = validate_arm(arm)
            if command == "move_ee":
                checked_arm, pose, checked_speed = validate_move(checked_arm, pose_base, speed)
        except ValueError as exc:
            outcome = ActionResult(False, "invalid_command", str(exc))
        else:
            if command == "move_ee":
                outcome = self._backend.move_ee(checked_arm, pose, checked_speed)
            elif command == "open_gripper":
                outcome = self._backend.open_gripper(checked_arm)
            else:
                outcome = self._backend.close_gripper(checked_arm)
            after = self._backend.task_state()
            self._holding_arm = after.grasped_by or before.grasped_by or self._holding_arm
            lost_contact = before.grasped_by is not None and after.grasped_by is None
            released = command == "open_gripper" and checked_arm == before.grasped_by
            if outcome.success and lost_contact and not released:
                outcome = ActionResult(
                    False, "object_dropped", "Cube contact no longer indicates a secure hold"
                )

        self._sim_step_count += 1
        self._history.append(
            {
                "step": self._sim_step_count,
                "action": command,
                "arm": arm if isinstance(arm, str) and arm in ("left", "right") else None,
                **asdict(outcome),
            }
        )
        return outcome
