# TRON2 仿真运行与验收

按 **Mock → MuJoCo S1 → MuJoCo S2** 的顺序运行 Cube Lift 和 Pick & Place。三种配置共用任务工具和手写 Oracle，S1 和 S2 共用同一套物理场景。[架构和工具约定](tron2_architecture.md) · [真机接入路线](tron2_hardware.md)

| 配置 | 物体位置来源 | 验证目标 |
| --- | --- | --- |
| [`*_mock.yaml`](../env_configs/tron2/) | 内存中的模拟状态 | 代码执行、动作反馈和重试。 |
| [`*_s1.yaml`](../env_configs/tron2/) | 仿真真值 | DACH_TRON2A 模型上的运动、物理接触和抓放。 |
| [`*_s2.yaml`](../env_configs/tron2/) | RGB-D 中心估计 | 通过视觉定位后的抓放。 |

## 1. 安装与 Mock 验证

在仓库根目录用 Python 3.10–3.12 创建环境并安装 [TRON2 仿真依赖](../requirements-tron2.txt)。Oracle 用固定脚本离线执行任务。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tron2.txt

python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_mock.yaml \
  --use-oracle-code True --total-trials 1

python -m capx.envs.launch \
  --config-path env_configs/tron2/pick_place_mock.yaml \
  --use-oracle-code True --total-trials 1
```

确认两条命令的 `Task completed` 都为 1。Mock 结果用于检查代码执行和任务判定，物理抓放由 S1 和 S2 验证。

## 2. 用官方 DACH_TRON2A 模型评测

将 LimX 的机器人描述下载到仓库旁边。`TRON2_MJCF_PATH` 指向带 2F 夹爪的 `robot_grasper.xml`，保留同一模型目录下的 `meshes/`。本仓库的[桌面场景](../capx/envs/assets/tron2_tasks/tabletop.xml)由后端在加载时合并到官方模型。[LimX 仿真器](https://github.com/limxdynamics/tron2_mujoco_sim) · [固定版本的模型和许可](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71)

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

S1 默认无渲染，在本进程推进 MuJoCo，适合先检查工作空间、IK、夹持与释放。

## 3. 用 RGB-D 评测 S2

使用和 S1 相同的 `TRON2_MJCF_PATH`。S2 需要可用的 MuJoCo 渲染环境，先尝试用头部相机估计红色方块和绿色目标的中心，观测失败时再尝试外部相机。S2 对直立、已知尺寸的方块估计位置，旋转仍使用场景约定。

```bash
python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_s2.yaml \
  --use-oracle-code True --total-trials 20

python -m capx.envs.launch \
  --config-path env_configs/tron2/pick_place_s2.yaml \
  --use-oracle-code True --total-trials 20
```

`get_image` 可读取头部、双腕和外部相机的 RGB-D 快照。连续录像仍待接入，运行现有配置时保持 `record_video: false`。

## 4. 接入模型并检查失败反馈

Oracle 跑通后，可用任务配置接入 Chat Completions 端点评估实际模型。先从 S1 和一个试验开始，再与 S2 分开记录结果。

```bash
python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_s1.yaml \
  --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" --total-trials 1
```

任务配置把动作结果、失败原因和当前状态传给下一回合。可从 `all_responses.json` 查看模型是否根据失败反馈重新生成代码。当前执行器在本进程运行仿真代码，真机评测需按[真机接入路线](tron2_hardware.md)另行部署。

## 5. 验收记录

仿真基线使用 Python 3.12、MuJoCo 3.17.0 和 macOS arm64，经 CaP-X CLI 使用 Oracle 运行种子 1–20。CLI 以试验编号作为随机种子。

| 配置 | Cube Lift | Pick & Place |
| --- | ---: | ---: |
| Mock | 20/20 | 20/20 |
| MuJoCo S1 | 20/20 | 20/20 |
| MuJoCo S2 | 20/20 | 20/20 |

结果写入配置指定的输出路径，路径会包含模型名，Oracle 使用 `oracle`。在 `summaries.txt` 看 `Task completed`，它统计达到任务判据的次数。`Code generation success rate` 统计代码成功执行的比例。各试验目录的 `code.py`、`summary.txt` 和 `all_responses.json` 可用于复盘执行代码和多轮反馈。

回归覆盖固定种子复位、动作拒绝与限额、Oracle、S2 估计以及模拟模型空抓后在同一场景重试。上表是 Oracle 基线，实际模型与真机需要分别评测。

```bash
python -m pip install pytest
TRON2_TEST_RENDER=1 python -m pytest -q tests/tron2
```

未设置 `TRON2_MJCF_PATH` 时会跳过实际模型测试。默认跳过需要渲染的 S2 检查，可用上述开关启用。

## 6. 故障定位

| 现象 | 先检查 |
| --- | --- |
| 模型或网格找不到 | `TRON2_MJCF_PATH` 是否指向 `DACH_TRON2A/xml/robot_grasper.xml`，以及该 `xml/` 的同级 `meshes/` 是否完整。 |
| S2 相机无法渲染 | 先用同一台机器跑 S1，随后检查 MuJoCo 渲染环境。Linux 的启动器默认使用 EGL。 |
| `empty_grasp`、`ik_unreachable` 或 `collision` | 查看 `TRON2 feedback` 和试验日志，再读取当前 TCP 和物体位置。修改场景或运动参数时用相同种子复跑。 |
