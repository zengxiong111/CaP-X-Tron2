# TRON2 architecture and tools

CaP-X executes model-generated Python. The task environment manages turns and scoring, while Mock or MuJoCo executes motion.

[简体中文](tron2_architecture.md) · [Simulation guide](tron2_bringup.en.md)

## Contents

- [Execution flow](#execution-flow)
- [Tools and coordinate frames](#tools-and-coordinate-frames)
- [Tasks and multi-turn feedback](#tasks-and-multi-turn-feedback)

## Execution flow

| Layer | Responsibility |
| --- | --- |
| [Code task environment](../capx/envs/tasks/tron2/) | Supplies task prompts, Oracle programs, and failure feedback. |
| [Simulation environment](../capx/envs/simulators/tron2_mujoco.py) | Manages seeded resets, observations, turn and action budgets, scoring, and rewards. Each [YAML](../env_configs/tron2/) creates its own environment. |
| [Control tools](../capx/integrations/tron2/control.py) | Exposes six tools to generated Python. |
| [MuJoCo backend](../capx/integrations/tron2/mujoco_backend.py) | Loads the external official model, merges the [tabletop MJCF](../capx/envs/assets/tron2_tasks/tabletop.xml), and simulates motion, contacts, the gripper, and cameras. |

## Tools and coordinate frames

| Tool | Inputs and outputs |
| --- | --- |
| `get_robot_state()` | Dual-arm TCP poses, joints, grippers, grasp state, and timestamp. |
| `get_object_pose(name)` | Pose of `cube` or `target`. Raises `ObservationUnavailableError` if the observation fails. |
| `move_ee(arm, pose_base, speed=0.1)` | `left` or `right`, TCP pose in the base frame, and speed in m/s. Returns `success`, `code`, and `message`. |
| `open_gripper(arm)` / `close_gripper(arm)` | Operates the selected gripper and returns the same action result fields. |
| `get_image(camera_name)` | RGB, metric depth, intrinsics `K`, extrinsics `T_base_camera`, and timestamp for `head`, `overview`, `left_wrist`, or `right_wrist`. Requires rendering. |

All TCP and object poses use `robot_base` and the format `[x, y, z, qw, qx, qy, qz]`, with positions in meters. `T_base_camera` maps optical coordinates (right, down, forward) into the base frame, with `T_base_object = T_base_camera @ T_camera_object`.

S1 reads ground-truth poses. S2 estimates object centers from the head or overview camera using known colors and sizes, with an upright orientation convention. Vision guides the actions and the simulator's physical state determines scoring.

## Tasks and multi-turn feedback

| Task | Success criteria |
| --- | --- |
| Cube Lift | Maintain a grasp while raising the cube center by at least 7 cm. |
| Pick & Place | Grasp and release the cube. Its horizontal error from the target must be at most 3.5 cm and its vertical error at most 1.2 cm. |

Both tasks require a stable window of at least 0.25 seconds. `TRON2 feedback` passes action results and current state to later turns, and retries continue in the same scene. Validation covers live-model Cube Lift with ground-truth poses and MuJoCo replay of the saved program. [Evaluation results](tron2_bringup.en.md#results) · [Hardware integration guide in Chinese](tron2_hardware.md)
