"""MuJoCo backend with one controlled disturbance for Cube Lift evaluation."""

import json

import numpy as np

from .backends import ActionResult, Arm, Pose
from .mujoco_backend import MujocoBackend


class RecoveryMujocoBackend(MujocoBackend):
    """Shift the cube once, after the first approach with the right gripper open."""

    OFFSET_M = 0.075

    def __init__(self, *, alternate_offsets: bool = False) -> None:
        super().__init__(enable_render=True)
        self.disturbance: dict | None = None
        self._approach_pending = False
        self._alternate_offsets = alternate_offsets
        self._offset_xy = (self.OFFSET_M, 0.0)

    def reset(self, seed: int | None = None) -> None:
        super().reset(seed)
        self.disturbance = None
        self._approach_pending = False
        if self._alternate_offsets and seed is not None and seed % 2 == 0:
            self._offset_xy = (0.0, -self.OFFSET_M)
        else:
            self._offset_xy = (self.OFFSET_M, 0.0)

    def physics_state_bytes(self) -> bytes:
        """Capture integrator and actuator state for matching the first turn."""
        spec = self._mj.mjtState.mjSTATE_INTEGRATION
        state = np.empty(self._mj.mj_stateSize(self._model, spec))
        self._mj.mj_getState(self._model, self._data, state, spec)
        return b"".join(
            (
                state.tobytes(),
                self._targets.tobytes(),
                json.dumps(self._gripper_goal, sort_keys=True).encode(),
            )
        )

    def open_gripper(self, arm: Arm) -> ActionResult:
        result = super().open_gripper(arm)
        self._approach_pending = arm == "right" and result.success
        return result

    def close_gripper(self, arm: Arm) -> ActionResult:
        self._approach_pending = False
        return super().close_gripper(arm)

    def move_ee(self, arm: Arm, pose_base: Pose, speed: float) -> ActionResult:
        result = super().move_ee(arm, pose_base, speed)
        should_shift = (
            self._approach_pending
            and arm == "right"
            and result.success
            and self.disturbance is None
        )
        self._approach_pending = False
        if should_shift:
            translation = self._data.qpos[self._cube_joint : self._cube_joint + 3]
            before = translation.tolist()
            translation[:2] += self._offset_xy
            self._data.qvel[self._cube_dof : self._cube_dof + 3] = 0.0
            self._mj.mj_forward(self._model, self._data)
            self.disturbance = {
                "before_world_xyz": before,
                "after_world_xyz": translation.tolist(),
                "offset_world_xyz": [*self._offset_xy, 0.0],
                "sim_time": float(self._data.time),
            }
        return result
