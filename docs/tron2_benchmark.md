# TRON2 配对基准

用统一 MuJoCo 固定安装场景运行 Cube Lift 和 Pick & Place。桌面世界 Z 为 0.620 m，`base_Link` 世界 Z 为 1.070 m，安装高差为 0.450 m。

[English](tron2_benchmark.en.md) · [环境设置](tron2_bringup.md#setup)

## 目录

- [配置](#配置)
- [运行方法](#运行方法)
- [与 CaP-Bench 的对应](#与-cap-bench-的对应)

## 配置

| 项目 | 设置 |
| --- | --- |
| 场景 | 使用仿真下沉安装位承托原厂支座。安装位外地面世界 Z 为 0。桌面和机械臂链接保持原有定义。 |
| 仿真环境 | Linux、Python 3.12.3、MuJoCo 3.17.0。 |
| 右夹爪 | 抓取朝向在原值上增加 15°。 |
| 任务 | `cube_lift_s2_guided.yaml` 或 `pick_place_s2_guided.yaml` |
| 模型 | Qwen2.5-Coder-3B-Instruct，Transformers 本地端点，BF16 贪心解码。 [权重版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| 感知 | 头部 RGB-D，无法估计时可用 overview。使用相同的位姿服务和外参。 |
| 扰动 | 首个右臂接近成功后平移方块 75 mm，奇数种子沿 +X，偶数种子沿 −Y。 |
| 判分 | Cube Lift 记录夹持与举升稳定性。Pick & Place 记录释放后与目标的误差和物体稳定性。 |

在种子 41–44 的两项扰动任务中，右腕最小关节限位余量为 0.04610 rad（首轮）和 0.13373 rad（Oracle 恢复）。支座与安装板的几何贴合、上述姿态和余量均在仿真中验证。真机安装与安全余量仍需实测。

## 运行方法

按 [Quick Start](../README.md#快速开始) 准备模型和感知服务，在仿真环境中设置 `MUJOCO_GL=egl`、`CAPX_MODEL_NAME` 与 `CAPX_MODEL_URL`。从仓库根目录运行。将 `benchmark_task` 改为 `pick_place_s2_guided` 可复跑另一任务。每次复跑使用新输出目录。


```bash
benchmark_dir=outputs/tron2_benchmark
benchmark_task=cube_lift_s2_guided
benchmark_config="env_configs/tron2/${benchmark_task}.yaml"
benchmark_common=(
  --config "$benchmark_config"
  --start-seed 41 --trials 20 --offset-directions '+X,-Y'
  --perception-url http://127.0.0.1:8121
)
benchmark_model=(
  --model "$CAPX_MODEL_NAME" --server-url "$CAPX_MODEL_URL" --fail-fast-model
)
python -m capx.envs.evaluate_tron2_recovery "${benchmark_common[@]}" \
  --oracle --output "$benchmark_dir/$benchmark_task/oracle.json"
python -m capx.envs.evaluate_tron2_recovery "${benchmark_common[@]}" "${benchmark_model[@]}" \
  --single-turn --output "$benchmark_dir/$benchmark_task/single.json"
python -m capx.envs.evaluate_tron2_recovery "${benchmark_common[@]}" "${benchmark_model[@]}" \
  --output "$benchmark_dir/$benchmark_task/text.json"
python -m capx.envs.evaluate_tron2_recovery "${benchmark_common[@]}" "${benchmark_model[@]}" \
  --baseline "$benchmark_dir/$benchmark_task/text.json" --target-motion \
  --output "$benchmark_dir/$benchmark_task/vdm.json"
```

JSON 记录逐种子判分、首轮程序与物理状态摘要、帧哈希和恢复结果。三个模型评测组共享任务首轮程序。VDM 组读取文本组的首轮记录并核对配对条件。使用 `--perturbation none` 可评估关闭平移扰动时的常规完成率。

遮挡对照只运行文本和 VDM 两组。用 `capx.envs.evaluate_tron2_calibrated_occlusion` 替换这两个命令的模块，使用 `--trials 4`，并更换输出目录。其余参数相同。

## 本轮结果

### 头部相机无遮挡

两项任务均在种子 41–60 评测。表中是扰动触发后的最终成功数。三组模型试验的首轮程序、物理状态和 RGB 帧逐种子一致，全部首轮空抓。Oracle 使用手写程序，在相同种子上使用相同扰动。

| 任务 | Oracle 两轮 | Qwen 单轮 | Qwen 多轮文本 | Qwen 文本 + VDM | VDM 方向正确 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cube Lift | 20/20 | 0/20 | 20/20 | 20/20 | 20/20 |
| Pick & Place | 20/20 | 0/20 | 20/20 | 11/20 | 20/20 |

Pick & Place 的九个 VDM 恢复失败都沿用了抬升前的 TCP，且方向判断正确。诊断性回放只替换这九段程序里的一行，使其在举起方块后重新读取 TCP，九个失败均恢复成功。表中保留原始模型生成结果。该组种子 60 在独立进程中补跑，重用了相同基线，并通过首轮状态和帧哈希核验。

### 头部相机部分遮挡

对种子 41–44 复跑。VDM 判分使用头部相机 RGB，机械臂位姿工具可回退到 overview。

| 任务 | 多轮文本 | 文本 + VDM | VDM 方向正确 | VDM 无法判断 |
| --- | ---: | ---: | ---: | ---: |
| Cube Lift | 4/4 | 4/4 | 3/4 | 1/4 |
| Pick & Place | 4/4 | 3/4 | 2/4 | 2/4 |

无法判断的后帧只剩 3–6 个红色像素。Pick & Place 的种子 43 方向判断正确，但恢复程序沿用了抬升前的 TCP，未完成放置。四个种子只覆盖本次遮挡设置。

## 与 CaP-Bench 的对应

下表比较评估接口。任务、提示与试验数采用 TRON2 自己的协议。 [CaP-Bench 分档定义](https://arxiv.org/html/2603.22435v1#S3)

| 上游档位 | TRON2 对应 |
| --- | --- |
| S1 | 真值位姿、高层工具和一次程序执行 |
| S2 | RGB-D 位姿、高层工具和一次程序执行 |
| S3、S4 | 低层视觉与控制原语档位仍待接入 |
| M1 | 多轮文本恢复，保留当前仿真状态 |
| M2 | 多轮原始 RGB 输入仍待统一验证 |
| M3 | 目标跟踪 VDM 的局部对照。上游还要求 VLM 场景描述和任务完成判断 |
| M4 | 低层工具与 VDM 的组合仍待接入 |
