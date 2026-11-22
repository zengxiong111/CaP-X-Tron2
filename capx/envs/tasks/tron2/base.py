"""Shared CaP-X execution and Oracle code for TRON2 tabletop tasks."""

from __future__ import annotations

import json
from typing import Any

from gymnasium import Env

from capx.envs.simulators import TRON2_ENV_FACTORIES
from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.envs.tasks.base import CodeExecutionEnvBase

TOOL_GUIDANCE = """Use the right arm and these tools. Poses are in the robot base frame, as
[x, y, z, qw, qx, qy, qz] in meters with a wxyz unit quaternion. The TCP is centered
between the fingers. Read the grasp quaternion from get_robot_state()["grasp_quaternions"]["right"].
Read get_object_pose("cube") before planning. Open the fingers, approach from 0.09 m above
the cube center, then lower the TCP to the center and close the fingers. Check the
success field of each motion or gripper result. If an action fails, stop that sequence,
inspect the code and message, and read the current poses before retrying. A close
command alone does not confirm the cube was picked up. Verify that the cube rises as
you lift the TCP vertically. Write executable Python using the provided tools.
"""

# The Oracle uses the tools injected by CodeExecutionEnvBase, just like model code.
GRASP_AND_LIFT = """\
arm = "right"
cube = get_object_pose("cube")
grasp_quaternion = get_robot_state()["grasp_quaternions"][arm]


def require_success(result, stage):
    if not result["success"]:
        raise RuntimeError(f"{stage}: {result['code']}: {result['message']}")


def move_tcp(x, y, z, stage):
    pose = (x, y, z, *grasp_quaternion)
    require_success(move_ee(arm, pose), stage)


require_success(open_gripper(arm), "open before grasp")
x, y, z = cube[:3]
move_tcp(x, y, z + 0.09, "approach cube")
move_tcp(x, y, z, "lower to cube")
require_success(close_gripper(arm), "close around cube")
move_tcp(x, y, z + 0.12, "lift cube")
lifted_cube = get_object_pose("cube")
if lifted_cube[2] < z + 0.07:
    raise RuntimeError("The cube did not rise 0.07 m. Recheck the cube and gripper poses.")
"""


class Tron2CodeEnv(CodeExecutionEnvBase):
    """Pass structured TRON2 episode feedback through the CaP-X code loop."""

    task: str
    low_level_env: Tron2MujocoEnv

    def _build_low_level(
        self,
        src: Env | str,
        privileged: bool = False,
        enable_render: bool = True,
        viser_debug: bool = False,
    ) -> Tron2MujocoEnv:
        factory = TRON2_ENV_FACTORIES.get(src) if isinstance(src, str) else None
        if factory is None:
            low_level = super()._build_low_level(src, privileged, enable_render, viser_debug)
        else:
            # Every code task owns its episode state even within the same process.
            low_level = factory(
                privileged=privileged, enable_render=enable_render, viser_debug=viser_debug
            )
        if not isinstance(low_level, Tron2MujocoEnv):
            raise TypeError("TRON2 code tasks require a Tron2MujocoEnv")
        if low_level.task != self.task:
            raise ValueError(f"Cannot run {self.task!r} with TRON2 task {low_level.task!r}")
        return low_level

    def _exec_user_code(self, code: str) -> dict[str, Any]:
        result = super()._exec_user_code(code)
        self.low_level_env.finish_attempt()
        return result

    def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        obs, reward, terminated, _, info = super().step(action)
        episode = self.low_level_env.episode_info()
        info.update(episode)

        # The CaP-X retry prompt consumes console stdout and stderr.
        feedback = {
            "task_completed": episode["task_completed"],
            "episode_truncated": episode["episode_truncated"],
            "failure_reason": episode["failure_reason"],
            "last_action": episode["last_action"],
        }
        if state := obs.get("robot_state"):
            feedback["tcp_poses"] = state["tcp_poses"]
            feedback["grippers"] = state["grippers"]
        if "object_poses" in obs:
            feedback["object_poses"] = obs["object_poses"]
        info["stdout"] += f"\nTRON2 feedback: {json.dumps(feedback)}\n"
        return obs, float(reward), terminated, episode["episode_truncated"], info

    def close(self) -> None:
        self.low_level_env.close()
