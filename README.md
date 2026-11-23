# CaP-X-Tron2

CaP-X-Tron2 在 MuJoCo 中用 LimX DACH_TRON2A 双指夹爪执行模型生成的 Python。当前支持单臂 Cube Lift 和 Pick & Place。

[English](README.en.md) · [仿真运行指南](docs/tron2_bringup.md) · [工具与坐标系](docs/tron2_architecture.md)

[TRON2 Web 评估](docs/tron2_bringup.md#web-workflow)提供感知服务器、LLM 代理配置，以及 Cube Lift 和 Pick & Place 的运行入口。

## 目录

- [快速开始](#快速开始)
- [仿真结果](#仿真结果)
- [打开图形回放](#打开图形回放)
- [安装与评测](#安装与评测)
- [上游项目](#上游项目)

## 快速开始

先安装 TRON2 仿真依赖并设置 `TRON2_MJCF_PATH`。从仓库根目录运行，前两步各用一个终端。也可以从 Web 的 `/tron2` 页面完成服务检查与评估。 [环境设置](docs/tron2_bringup.md#setup) · [Web 评估](docs/tron2_bringup.md#web-workflow)

1. 启动 TRON2 RGB-D 感知服务。

   ```bash
   python -m capx.serving.launch_tron2_rgbd_server --port 8121
   ```

2. 启动 OpenAI 兼容的 LLM 服务。已有本地服务可以直接复用。下方命令适用于已安装 vLLM 的模型环境。 [vLLM 安装](https://docs.vllm.ai/en/latest/getting_started/installation/)

   ```bash
   python -m capx.serving.vllm_server \
     --model Qwen/Qwen2.5-Coder-3B-Instruct \
     --revision 488639f1ff808d1d3d0ba301aef8c11461451ec5 \
     --host 127.0.0.1 --port 18086 --max-model-len 4096
   ```

3. 运行一个种子的 Cube Lift 恢复评测。复跑时使用新的输出路径。

   ```bash
   export MUJOCO_GL=egl
   python -m capx.envs.evaluate_tron2_recovery \
     --config env_configs/tron2/cube_lift_s2_guided.yaml \
     --model Qwen/Qwen2.5-Coder-3B-Instruct \
     --server-url http://127.0.0.1:18086/v1/chat/completions \
     --perception-url http://127.0.0.1:8121 \
     --start-seed 41 --trials 1 --offset-directions '+X,-Y' \
     --output outputs/tron2_smoke/text.json
   ```

## 仿真结果

当前固定安装场景下，两项任务的 Qwen 多轮文本均为 **20/20**。加入 VDM 后，Cube Lift 为 **20/20**，Pick & Place 为 **11/20**。 [配对协议与结果](docs/tron2_benchmark.md#本轮结果)

以下发布记录使用支座统一前的布局。常规实验使用 0.590 m 高差，遮挡试验另用 0.450 m 高差的临时布局。 [场景与复跑说明](docs/tron2_bringup.md#results)

Cube Lift 的手写 Oracle 在 Mock、MuJoCo 真值和 RGB-D 三种配置中均复跑至 **20/20**。使用相同的 20 个种子，实际 Qwen2.5-Coder-3B-Instruct 结果如下。

| MuJoCo 真值配置 | 单轮 | 多轮 |
| --- | ---: | ---: |
| 原始提示词 | 0/20 | 0/20 |
| 明确五步动作及脚本格式 | 20/20 | 20/20 |

原始程序在闭爪后缺少抬升指令。明确动作后，每个试验都在首轮成功，方块中心升高 11.95–11.97 cm。统计采用仿真物理判分。 [评测口径与环境](docs/tron2_bringup.md#results)

固定 +X 偏移下，真值位置、RGB-D 文本和 RGB-D 文本 + SmolVLM 三组均从首轮 **0/20** 恢复到 **20/20**。在 +X 和 −Y 的配对评测中，目标跟踪版 VDM 判对 **20/20** 个图像移动方向，文本组和文本 + VDM 组均恢复 **20/20**。 [恢复结果与复跑命令](docs/tron2_recovery.md)

另在 **0.450 m 安装高差**的独立布局中加入头部相机遮挡。20 对新种子全部恢复，VDM 判对 **20/20** 个方向。 [遮挡评测、复跑命令与安装限制](docs/tron2_calibrated_occlusion.md)

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
