# CaP-X-Tron2

CaP-X-Tron2 在 MuJoCo 中用 LimX DACH_TRON2A 双指夹爪执行模型生成的 Python。当前支持单臂 Cube Lift 和 Pick & Place。

[English](README.en.md) · [仿真运行指南](docs/tron2_bringup.md) · [工具与坐标系](docs/tron2_architecture.md)

## 目录

- [仿真结果](#仿真结果)
- [打开图形回放](#打开图形回放)
- [安装与评测](#安装与评测)
- [上游项目](#上游项目)

## 仿真结果

Cube Lift 的手写 Oracle 在 Mock、MuJoCo 真值和 RGB-D 三种配置中均复跑至 **20/20**。使用相同的 20 个种子，实际 Qwen2.5-Coder-3B-Instruct 结果如下。

| MuJoCo 真值配置 | 单轮 | 多轮 |
| --- | ---: | ---: |
| 原始提示词 | 0/20 | 0/20 |
| 明确五步动作及脚本格式 | 20/20 | 20/20 |

原始程序在闭爪后缺少抬升指令。明确动作后，每个试验都在首轮成功，方块中心升高 11.95–11.97 cm。统计采用仿真物理判分。 [评测口径与环境](docs/tron2_bringup.md#results)

固定 +X 偏移下，真值位置、RGB-D 文本和 RGB-D 文本 + SmolVLM 三组均从首轮 **0/20** 恢复到 **20/20**。在 +X 和 −Y 的配对评测中，目标跟踪版 VDM 判对 **20/20** 个图像移动方向，文本组和文本 + VDM 组均恢复 **20/20**。 [恢复结果与复跑命令](docs/tron2_recovery.md)

## 打开图形回放

完成[环境与模型设置](docs/tron2_bringup.md#setup)后，在仓库根目录运行以下命令。MuJoCo 会执行已通过验收的模型代码，按 **R** 重播。

```bash
MUJOCO_GL=glfw python -m capx.envs.replay_tron2_cube_lift
```

## 安装与评测

- [安装仿真依赖并获取官方机器人模型](docs/tron2_bringup.md#setup)
- [跑手写 Oracle](docs/tron2_bringup.md#oracle)和[复跑真实模型的单轮、多轮对照](docs/tron2_bringup.md#model-eval)
- [工具、坐标系与任务判据](docs/tron2_architecture.md) · [真机接入路线](docs/tron2_hardware.md)

## 上游项目

[CaP-X 源码与上游环境设置](https://github.com/capgym/cap-x) · [CaP-X 论文](https://arxiv.org/abs/2603.22435) · [MIT 许可证](LICENSE)
