# TRON2 仿真运行与验收

在 MuJoCo 中回放 Cube Lift，运行手写 Oracle，并对比真实代码模型的单轮和多轮表现。本文命令均在仓库根目录运行。

[English](tron2_bringup.en.md) · [工具与坐标系](tron2_architecture.md)

## 目录

- [环境与官方模型](#setup)
- [Web 评估](#web-workflow)
- [MuJoCo 图形回放](#replay)
- [Oracle 基线](#oracle)
- [真实模型对照](#model-eval)
- [验收结果](#results)

<a id="setup"></a>
<a id="2-用官方-dach_tron2a-模型评测"></a>

## 环境与官方模型

1. 用 Python 3.10–3.12 建立独立环境。下方命令安装 TRON2 仿真依赖。

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements-tron2.txt
   ```

2. 将官方 DACH_TRON2A 模型和网格存放在仓库旁边。Mock 可直接跳到 [Oracle 基线](#oracle)。[LimX 模型与许可](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71)

   ```bash
   git clone --filter=blob:none --no-checkout \
     https://github.com/limxdynamics/tron2-robot-description.git ../tron2-robot-description
   git -C ../tron2-robot-description sparse-checkout set --no-cone \
     '/LICENSE' '/tron2a/DACH_TRON2A/xml/robot_grasper.xml' '/tron2a/DACH_TRON2A/meshes/'
   git -C ../tron2-robot-description checkout --detach 9939c22e69d27653ec0ba8a505859a2903dd1a71
   export TRON2_MJCF_PATH="$PWD/../tron2-robot-description/tron2a/DACH_TRON2A/xml/robot_grasper.xml"
   ```

<a id="web-workflow"></a>

## Web 评估

完成仿真环境和官方模型设置后，使用 Node.js 和 npm 构建现有 CaP-X Web 界面。Web 和 CLI 使用同一固定安装场景，桌面世界 Z 为 0.620 m，安装高差为 0.450 m。 [场景与基准](tron2_benchmark.md#配置)

```bash
npm ci --prefix web-ui
npm run build --prefix web-ui
python -m capx.web.server --host 127.0.0.1 --port 8200
```

从仿真电脑打开 [TRON2 评估页](http://127.0.0.1:8200/tron2)，按页面三个步骤运行。

1. 点击 **启动感知服务器**。TRON2 RGB-D 服务默认使用 8121 端口。评估中的 `get_object_pose` 会把相机帧发送给该服务，必要时切换到 overview 相机。
2. 在 **设置 LLM 代理** 填入已运行的本地 Chat Completions 完整地址与模型 ID，点击 **测试 LLM 连接**。页面默认填写本地 Qwen2.5-Coder-3B-Instruct 和 18086 端口。可按需要使用 CaP-X 的 OpenRouter 或 vLLM 服务。 [LLM 代理设置](configuration.md#adding-new-llm-providers)
3. 选择任务、反馈方式、起始种子与试验数，点击 **运行评估**。选择配对 VDM 时，页面先运行文本基线，再核对并运行 VDM 组。页面显示 MuJoCo 画面、物理判分和生成程序。**停止评估**结束已启动的试验进程。报告与图像默认写入 `outputs/tron2_web/`。

任务菜单提供 Cube Lift 和 Pick & Place。可选择头部相机部分遮挡。选择 Oracle 时可以跳过 LLM 配置。 [CLI 配对基准](tron2_benchmark.md#运行方法)

<a id="replay"></a>

## MuJoCo 图形回放

在有图形桌面的 Linux 上，使用 MuJoCo 3.17.0 运行经验证的种子 1。程序直接执行已保存的模型代码。窗口显示仿真判分和抬升高度，按 **R** 重播。[模型生成的程序](../capx/envs/assets/tron2_tasks/cube_lift_qwen.txt)

```bash
MUJOCO_GL=glfw python -m capx.envs.replay_tron2_cube_lift
```

启动感知服务后，可用同一评测 YAML 回放 Pick & Place 的 Oracle。使用 `--program` 可改为执行保存的 Python 程序。图形回放使用单轮、无扰动场景。

```bash
MUJOCO_GL=glfw python -m capx.envs.replay_tron2_cube_lift \
  --config env_configs/tron2/pick_place_s2_guided.yaml --oracle --seed 41
```

<a id="oracle"></a>

## Oracle 基线

Cube Lift 的三份配置分别使用 Mock、仿真真值位姿和 RGB-D 估计。S2 通过 YAML 的 `api_servers` 自动启动或复用本机感知服务。Linux 启动器默认使用 EGL。运行 Pick & Place 时将配置文件名中的 `cube_lift` 换成 `pick_place`。

```bash
for mode in mock s1 s2; do
  python -m capx.envs.launch \
    --config-path "env_configs/tron2/cube_lift_${mode}.yaml" \
    --use-oracle-code True --total-trials 20
done
```

用 `TRON2_TEST_RENDER=1 python -m pytest -q tests/tron2` 运行含 RGB-D 的回归检查。环境需安装 `pytest` 并设置 `TRON2_MJCF_PATH`。

<a id="model-eval"></a>

## 真实模型对照

连接已运行的 OpenAI 兼容 Chat Completions 端点。`CAPX_MODEL_URL` 是完整端点 URL，`CAPX_MODEL_NAME` 是端点接受的模型 ID。此次使用本地 Qwen2.5-Coder-3B-Instruct 和 BF16 贪心解码。[模型权重复现版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) · [端点配置](configuration.md#adding-new-llm-providers)

```bash
for config in cube_lift_s1_single cube_lift_s1 cube_lift_s1_guided_single cube_lift_s1_guided_multi; do
  python -m capx.envs.launch \
    --config-path "env_configs/tron2/${config}.yaml" \
    --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
    --temperature 0 --max-tokens 768 --total-trials 20
done
```

四份配置使用种子 1–20 和仿真真值位姿。每种提示词的两组共享初始提示和动作预算。单轮允许一次代码执行，多轮最多六次。`summaries.txt` 的 `Task completed` 对应物理成功数，`all_responses.json` 记录生成与重试。

<a id="results"></a>
<a id="5-验收记录"></a>

## 验收结果

下表是支座统一前使用 0.590 m 高差的历史记录。当前固定安装布局的验证单独记录。 [固定安装基准](tron2_benchmark.md)

| 评测 | 结果 |
| --- | --- |
| Cube Lift Oracle 重跑 | Mock、MuJoCo S1、MuJoCo S2 均为 20/20 |
| 原始提示词 | 单轮和多轮均为 0/20，程序闭爪后缺少抬升指令，多轮每次均重写五次 |
| 明确五步动作及脚本格式 | 单轮和多轮均为 20/20，全部首轮完成，方块中心升高 11.95–11.97 cm |
| TRON2 回归 | 8 项通过，含 S2 注入 MuJoCo 后端的检查 |

Cube Lift 判分要求方块保持夹持，中心升高至少 7 cm，并在 0.25 秒稳定窗口内保持速度不高于 0.04 m/s。验收使用源码 `ce2e708228badee5ba601ebcc03f6aaa069d33cf`、Linux、Python 3.12.3、MuJoCo 3.17.0 和桌面世界高度 0.620 m。发布的回放程序 SHA-256 为 `2d7ad6a562b64e03d9179b0980c122044cdf6b783bf6a70f842553ca47531881`。

仓库此前记录的 Pick & Place Oracle 在同三种配置上均为 20/20。真实模型验证覆盖 Cube Lift 的真值位姿和 RGB-D 恢复。图形回放执行保存的程序。 [扰动与 VDM 评测](tron2_recovery.md)
