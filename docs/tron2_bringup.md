# CaP-X-Tron2 实施与验收

本仓库通过 CaP-X 运行 **Cube Lift** 和 **Pick & Place**。先用 Mock 检查工具调用、任务判定与失败重试，再用官方 DACH_TRON2A 模型验证 MuJoCo 接触，最后使用 RGB-D 估计的位置执行相同任务。三种配置运行同一份 Oracle，也可以通过同一个 CaP-X 入口调用模型。

| 配置 | 观测与运动 | 用途 |
| --- | --- | --- |
| `cube_lift_mock.yaml` / `pick_place_mock.yaml` | 可重复的内存状态与模拟抓放 | 快速检查代码执行和错误反馈 |
| `cube_lift_s1.yaml` / `pick_place_s1.yaml` | MuJoCo 接触物理与仿真真值位姿 | 检查 DACH_TRON2A 双臂的运动，以及单臂抓放 |
| `cube_lift_s2.yaml` / `pick_place_s2.yaml` | MuJoCo 接触物理与 RGB-D 中心估计 | 检查不使用仿真真值位姿的抓放 |

## 1. 安装和验证工具链

在仓库根目录使用 Python 3.10–3.12 创建环境。TRON2 的本地评测只需 `requirements-tron2.txt` 中的依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tron2.txt

python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_mock.yaml \
  --use-oracle-code True --total-trials 2

python -m capx.envs.launch \
  --config-path env_configs/tron2/pick_place_mock.yaml \
  --use-oracle-code True --total-trials 2
```

Mock 的成果仅用于检查软件路径。评测输出中的 `Task completed` 才是达到任务判据的次数。`Code generation success rate` 统计代码执行成功的比例。

## 2. 用官方 DACH_TRON2A 模型评测

模型与网格保存在 `tron2-robot-description`。这里使用 LimX 仿真器固定引用的版本，将资产放在仓库外，由 `TRON2_MJCF_PATH` 指向带 2F 夹爪的 `robot_grasper.xml`。资产由 LimX 发布，适用上游 Apache-2.0 许可。[LimX 仿真器](https://github.com/limxdynamics/tron2_mujoco_sim) · [固定版本的模型和许可](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71)

```bash
git clone --filter=blob:none --no-checkout \
  https://github.com/limxdynamics/tron2-robot-description.git ../tron2-robot-description
git -C ../tron2-robot-description sparse-checkout set --no-cone \
  '/LICENSE' '/tron2a/DACH_TRON2A/xml/robot_grasper.xml' '/tron2a/DACH_TRON2A/meshes/'
git -C ../tron2-robot-description checkout --detach 9939c22e69d27653ec0ba8a505859a2903dd1a71
export TRON2_MJCF_PATH="$PWD/../tron2-robot-description/tron2a/DACH_TRON2A/xml/robot_grasper.xml"

python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_s1.yaml \
  --use-oracle-code True --total-trials 20

python -m capx.envs.launch \
  --config-path env_configs/tron2/pick_place_s1.yaml \
  --use-oracle-code True --total-trials 20
```

CLI 以试验编号作为随机种子，将过程和汇总写入 `outputs/`。仿真在本进程加载机械模型并推进物理帧。SDK 通信桥、机器人控制器和网络均不参与此路径。

## 3. 用 RGB-D 评测 S2

S2 使用头部相机检测红色方块和绿色目标。头部观测失败时尝试外部相机。估计器用深度、内参和当前相机外参把像素投影到机器人基座坐标系，针对已知尺寸的直立方块估计中心。返回的四元数是直立场景约定，旋转没有从图像测量。两台相机都无法估计时，工具会明确报告观测失败。

```bash
python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_s2.yaml \
  --use-oracle-code True --total-trials 20

python -m capx.envs.launch \
  --config-path env_configs/tron2/pick_place_s2.yaml \
  --use-oracle-code True --total-trials 20
```

S2 需要 MuJoCo 渲染环境。`get_image` 可读取头部、双腕和外部相机的 RGB-D 快照。S1 和 Mock 的默认配置不需要创建渲染上下文。TRON2 当前提供快照，CaP-X 的连续录像选项尚未接入。

## 4. 接入模型并检查失败反馈

用同一份 S1 配置，传入可访问的 Chat Completions 端点与模型名。

```bash
python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_s1.yaml \
  --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" --total-trials 1
```

六个工具使用同一个 `robot_base` 坐标系。位姿为 `[x, y, z, qw, qx, qy, qz]`，位置单位为米。`move_ee`、`open_gripper`、`close_gripper` 返回 `success`、`code` 和 `message`。脚本应在动作失败后读取结果，重新观察机器人与方块，再决定下一步。CaP-X 也会把回合状态连同标准输出和异常传给模型，用于生成下一回合代码。

方块由指尖的物理接触夹持。Lift 要求方块比初始高度高至少 7 cm 并稳定握持至少 0.25 秒。Pick & Place 要求执行过夹持与释放，且方块在半径 3.5 cm 的目标区内稳定至少 0.25 秒。RGB-D 接口返回米制深度、相机内参 `K`、`T_base_camera` 和时间戳。外参把右、下、前分别为正 X、Y、Z 的光学坐标变换到 `robot_base`。

## 5. 验收记录

Python 3.12、MuJoCo 3.17.0、macOS arm64，经 CaP-X CLI 使用 Oracle 跑种子 1–20。

| 配置 | Cube Lift | Pick & Place |
| --- | ---: | ---: |
| Mock | 20/20 | 20/20 |
| MuJoCo S1 | 20/20 | 20/20 |
| MuJoCo S2 | 20/20 | 20/20 |

回归测试用固定的模型响应触发一次空抓，检查下一回合收到失败原因，并在同一场景完成抬升。实际语言模型的生成质量需要用自己的模型端点评估。

```bash
python -m pip install pytest
TRON2_TEST_RENDER=1 python -m pytest -q tests/tron2
```

未设置 `TRON2_MJCF_PATH` 时会跳过实际模型测试。默认跳过需要渲染的 S2 检查，可用上述开关启用。

## 6. 真机里程碑

真机传输使用 [LimX tron2_env](https://github.com/limxdynamics/tron2_env) 的 WebSocket 运行时。一台有对应型号、夹爪、相机和急停的设备，以及测得的 TCP、工作空间、关节和速度/力限制，是调试前提。实施时将机器人运动放在独立服务，在本地由受限高层 API 执行。先在监督下测试空载运动、超时、掉线、碰撞和人工复位，再运行固定 Oracle 并保留结果。当前 CaP-X 执行器在本进程运行 Python，仅用于可信仿真；仓库未注册真机执行环境。
