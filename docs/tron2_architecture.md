# TRON2 架构与工具

CaP-X 执行模型生成的 Python。任务环境管理回合与判分，运动由 Mock 或 MuJoCo 后端执行。

[English](tron2_architecture.en.md) · [仿真运行与验收](tron2_bringup.md)

## 目录

- [执行流程](#执行流程)
- [工具和坐标约定](#工具和坐标约定)
- [任务与多轮反馈](#任务与多轮反馈)

## 执行流程

| 层 | 职责 |
| --- | --- |
| [任务代码环境](../capx/envs/tasks/tron2/) | 提供任务提示、Oracle 和失败反馈。 |
| [仿真环境](../capx/envs/simulators/tron2_mujoco.py) | 负责种子复位、观测、回合与动作预算、判分和奖励。每份 [YAML](../env_configs/tron2/) 构造独立环境。 |
| [控制工具](../capx/integrations/tron2/control.py) | 将六个工具暴露给生成的 Python。 |
| [MuJoCo 后端](../capx/integrations/tron2/mujoco_backend.py) | 加载外部官方模型并合并[桌面 MJCF](../capx/envs/assets/tron2_tasks/tabletop.xml)，推进运动、接触、夹爪和相机。 |

## 工具和坐标约定

| 工具 | 参数与结果 |
| --- | --- |
| `get_robot_state()` | 双臂 TCP、关节、夹爪、夹持状态和时间戳。 |
| `get_object_pose(name)` | `cube` 或 `target` 的位姿。观测失败时抛出 `ObservationUnavailableError`。 |
| `move_ee(arm, pose_base, speed=0.1)` | `left` 或 `right`、基座系 TCP 位姿、速度（m/s）。返回 `success`、`code`、`message`。 |
| `open_gripper(arm)` / `close_gripper(arm)` | 操作指定手臂的夹爪，返回相同的动作结果结构。 |
| `get_image(camera_name)` | `head`、`overview`、`left_wrist` 或 `right_wrist` 的 RGB、米制深度、内参 `K`、外参 `T_base_camera` 和时间戳。需启用渲染。 |

所有 TCP 和物体位姿都在 `robot_base` 系，格式为 `[x, y, z, qw, qx, qy, qz]`，位置单位为米。`T_base_camera` 将光学系（右、下、前）变换到基座系，`T_base_object = T_base_camera @ T_camera_object`。

S1 读取真值位姿。S2 用头部或外部相机估计已知颜色与尺寸的物体中心，旋转采用直立场景约定。视觉定位驱动动作，任务得分来自仿真物理状态。

## 任务与多轮反馈

| 任务 | 成功条件 |
| --- | --- |
| Cube Lift | 持续夹持，方块中心升高至少 7 cm。 |
| Pick & Place | 曾夹持且已释放。方块距目标的水平误差至多 3.5 cm，垂直误差至多 1.2 cm。 |

两项任务均要求至少 0.25 秒稳定窗口。`TRON2 feedback` 将动作结果和当前状态提供给后续回合，重试沿用当前场景。已验证真实模型在真值位姿配置下的 Cube Lift，以及保存代码的 MuJoCo 回放。 [评测结果](tron2_bringup.md#results) · [真机接入路线](tron2_hardware.md)
