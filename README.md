# CaP-X-Tron2

CaP-X-Tron2 将 [CaP-X](https://github.com/capgym/cap-x) 的代码执行框架用于 LimX TRON2 的桌面操作，目前在 MuJoCo 中验证从任务指令到机器人动作的流程。Agent 生成 Python，通过统一工具读取状态、定位物体、移动末端和控制夹爪。执行失败时，CaP-X 会把失败原因和当前状态送回下一回合，让 Agent 重新观察并尝试。

当前使用官方 **DACH_TRON2A** 模型和双指夹爪，验证两项单臂桌面任务。

- **Cube Lift**：夹起方块，让方块中心升高至少 7 cm，并稳定握持至少 0.25 秒。
- **Pick & Place**：夹取并移动方块，释放后让方块在目标区稳定至少 0.25 秒。

[仿真运行与验收](docs/tron2_bringup.md) · [架构与工具](docs/tron2_architecture.md) · [真机接入路线](docs/tron2_hardware.md)

## 当前进展

同一份手写参考程序（Oracle）通过 CaP-X CLI 运行。每个配置和任务组合都使用种子 1–20。

| 配置 | 物体位置来源 | Cube Lift | Pick & Place |
| --- | --- | ---: | ---: |
| Mock | 内存中的模拟状态，验证工具与任务流程 | 20/20 | 20/20 |
| MuJoCo S1 | 仿真真值位姿，验证指尖接触、夹持和释放 | 20/20 | 20/20 |
| MuJoCo S2 | RGB-D 估计红色方块和绿色目标的中心，验证视觉定位后的抓放 | 20/20 | 20/20 |

7 项 TRON2 回归测试通过。测试中，模拟模型先在空处闭爪，下一回合收到 `empty_grasp` 和新的观测，再在同一场景完成抬升。表中的完成数是 **Oracle 仿真基线**，实际语言模型和真机尚未评测。[验收环境与复现步骤](docs/tron2_bringup.md#5-验收记录)

## 仓库结构

```text
capx/
├── envs/
│   ├── assets/tron2_tasks/        # 自有桌面、方块、目标区和外部相机 MJCF
│   ├── simulators/tron2_mujoco.py  # 环境、回合状态和任务判据
│   └── tasks/tron2/              # 任务提示、Oracle 和失败反馈
├── integrations/tron2/           # 统一工具、Mock、MuJoCo、RGB-D 和指令检查
└── third_party/                  # 上游 CaP-X 依赖子模块
env_configs/tron2/                # 两项任务的 Mock、S1、S2 配置
tests/tron2/                      # 工具调用、重试和仿真回归
docs/tron2_*.md                    # 仿真运行、工具契约和真机路线
requirements-tron2.txt            # TRON2 仿真评测依赖
```

## 快速开始

在仓库根目录用 Python 3.10–3.12 创建环境。先跑一次离线 Mock，确认任务配置和工具调用可用。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tron2.txt
python -m capx.envs.launch \
  --config-path env_configs/tron2/cube_lift_mock.yaml \
  --use-oracle-code True --total-trials 1
```

运行 S1 或 S2 前，获取固定版本的官方模型并设置 `TRON2_MJCF_PATH`。机器人模型与网格保存在外部目录，项目自有场景随仓库分发。S2 还需要可用的 MuJoCo 渲染环境。[模型下载和仿真命令](docs/tron2_bringup.md#2-用官方-dach_tron2a-模型评测)

## 未完成

| 工作 | 下一步 |
| --- | --- |
| 实际模型评测 | 接通实际语言模型端点，测量生成代码的任务完成率、重试次数和主要失败原因。 |
| S2 视觉泛化 | 当前使用固定场景中的颜色和尺寸先验。还需验证光照、遮挡和未标记物体，并加入完整 6D 位姿估计。 |
| 真机接入与联调 | 实现 `tron2_real.py` 和独立运动服务，完成标定与保护测试后先验证真机 Oracle。[接入顺序](docs/tron2_hardware.md#验收顺序) |
| 连续录像 | 目前可读取 RGB-D 快照，还需为每回合接入连续录像及其时间戳。 |

## 上游 CaP-X

本项目沿用上游 CaP-X 的代码执行和评测框架。以下是上游环境的安装、运行和扩展入口。

<details>
<summary>展开上游 CaP-X 说明</summary>

[Project Page](https://capgym.github.io/) &ensp;|&ensp; [Paper](https://arxiv.org/abs/2603.22435) 

**Max Fu<sup>&#42;,1,2</sup>, Justin Yu<sup>&#42;,2</sup>, Karim El-Refai<sup>&#42;,2</sup>, Ethan Kou<sup>&#42;,2</sup>, Haoru Xue<sup>&#42;,1,2</sup>,
Huang Huang<sup>3</sup>, Wenli Xiao<sup>4</sup>, Guanzhi Wang<sup>1</sup>, Fei-Fei Li<sup>3</sup>, Guanya Shi<sup>4</sup>, Jiajun Wu<sup>3</sup>,
Shankar Sastry<sup>2</sup>, Yuke Zhu<sup>1</sup>, Ken Goldberg<sup>&dagger;,2</sup>, Jim Fan<sup>&dagger;,1</sup>**

<sup>1</sup>NVIDIA &ensp; <sup>2</sup>UC Berkeley &ensp; <sup>3</sup>Stanford University &ensp; <sup>4</sup>Carnegie Mellon University

<sup>&#42;</sup>Equal contribution &ensp; <sup>&dagger;</sup>Equal advising



---
**CaP-X** is an open-access framework for systematically studying Code-as-Policy agents in robot manipulation. It consists of four components:


| Component      | What it does                                                                                                                                                                                   |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CaP-Gym**    | Interactive Gymnasium environments where agents control robots by generating Python code that composes perception and control primitives. 39 tasks across Robosuite, LIBERO-PRO, and BEHAVIOR. |
| **CaP-Bench**  | Systematic benchmark evaluating coding agents across abstraction levels, interaction modes, and visual grounding modalities. 8 tiers (S1-S4 single-turn, M1-M4 multi-turn).                    |
| **CaP-Agent0** | Training-free agentic framework with multi-turn visual differencing, auto-synthesized skill libraries, and parallel ensembled reasoning.                                                       |
| **CaP-RL**     | Reinforcement learning on the coding agent via GRPO, using environment rewards to post-train language models. Transfers from sim to real with minimal gap.                                     |


---

## Upstream CaP-X installation

CaP-X uses [uv](https://docs.astral.sh/uv/) for dependency management. Requires **Python 3.10** and a **CUDA-capable GPU**.

```bash
git clone --recurse-submodules https://github.com/capgym/cap-x && cd cap-x

# Or if already cloned without --recurse-submodules:
git submodule update --init --recursive

# Install uv (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh

uv python install 3.10 && uv venv -p 3.10

# Base install
uv sync
```

### Simulator-specific setup

Pick **one** simulator family to install, as Robosuite (1.5.0) and LIBERO (`robosuite==1.4.0`) would be in conflict.

#### Robosuite

```bash
uv sync --extra robosuite
```

#### LIBERO-PRO

LIBERO requires a **separate virtual environment**.

```bash
uv venv .venv-libero --python 3.12
source .venv-libero/bin/activate
uv sync --active --extra libero --extra contactgraspnet
```

See [docs/libero-tasks.md](docs/libero-tasks.md) for running any of 130+ LIBERO tasks.

#### BEHAVIOR (Isaac Sim)

BEHAVIOR tasks run on NVIDIA Isaac Sim via OmniGibson. Requires Python 3.10 and CUDA 12.x.

```bash
cd capx/third_party/b1k
./uv_install.sh --dataset          # installs OmniGibson, Isaac Sim, BDDL, cuRobo, and downloads assets
cd ../../..                        # back to repo root

# Post-install fix — copy cuRobo JIT headers (run with b1k venv active)
source capx/third_party/b1k/.venv/bin/activate
cp capx/third_party/curobo/src/curobo/curobolib/cpp/*.h \
   $(python -c "import sysconfig; print(sysconfig.get_path('purelib'))")/curobo/curobolib/cpp/
```

> The `--dataset` flag downloads robot assets, BEHAVIOR-1K scene/object assets, and 2025 challenge task instances. You will be prompted to accept the NVIDIA Isaac Sim EULA and BEHAVIOR dataset license. To auto-accept, add `--accept-dataset-tos`.

For headless servers:
```bash
sudo apt-get update && sudo apt-get install -y libegl1 libgl1
# Remove duplicate Vulkan ICD if present (causes segfault on multi-GPU systems)
sudo rm -f /usr/share/vulkan/icd.d/nvidia_icd.json
```

See [docs/behavior-tasks.md](docs/behavior-tasks.md) for task details and expected baselines.

### Optional extras

```bash
uv sync --extra verl             # RL training with VeRL/GRPO
uv sync --extra contactgraspnet  # Contact-GraspNet grasp planning
uv sync --extra curobo           # cuRobo GPU-accelerated IK & motion planning (requires CUDA)
```

## Quick Start

### 1. Perception servers (auto-launched)

Perception servers (SAM3, ContactGraspNet, PyRoKi) are **auto-launched** by the YAML config when you run an evaluation. No manual setup required for most configs.

> **SAM3 authentication:** SAM3 weights require HuggingFace access. Request access at the [SAM3 repo](https://github.com/facebookresearch/sam3), then authenticate locally with `huggingface-cli login`. Weights are cached after first download.

To pre-launch servers (e.g. for sharing across multiple eval runs):

```bash
# Start SAM3 + GraspNet + PyRoKi with automatic GPU allocation
uv run --no-sync --active capx/serving/launch_servers.py --profile default
```

Use `--dry-run` to preview the allocation. Other profiles:

```bash
--profile full      # All perception servers (SAM3, GraspNet, PyRoKi, OWL-ViT, SAM2)
--profile minimal   # PyRoKi only (for oracle/privileged evals)
```

### 2. Set up an LLM proxy

The evaluation harness queries an LLM through a local proxy that exposes an OpenAI-compatible API.

```bash
# OpenRouter (get a key at openrouter.ai/keys)
echo "sk-or-v1-your-key-here" > .openrouterkey
uv run --no-sync --active capx/serving/openrouter_server.py --key-file .openrouterkey --port 8110
```

> **Note:** `.openrouterkey` are git-ignored. The default server URL in configs is `http://127.0.0.1:8110/chat/completions`. 

See [docs/configuration.md](docs/configuration.md) for all provider options (OpenRouter, vLLM, custom).

### 3. Run evaluation

```bash
# Robosuite: single-turn benchmark (100 trials, 12 parallel workers)
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/cube_stack/franka_robosuite_cube_stack.yaml \
    --model "google/gemini-3.1-pro-preview"

# Robosuite: multi-turn with visual differencing
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/cube_stack/franka_robosuite_cube_stack_multiturn_vdm.yaml \
    --model "google/gemini-3.1-pro-preview"

# LIBERO-PRO: spatial task (requires .venv-libero)
source .venv-libero/bin/activate
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/libero/franka_libero_spatial_0.yaml \
    --model "google/gemini-3.1-pro-preview"

# BEHAVIOR: R1Pro radio pickup (20 trials) — requires b1k venv
source capx/third_party/b1k/.venv/bin/activate
OMNI_KIT_ACCEPT_EULA=YES OMNIGIBSON_HEADLESS=1 \
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/r1pro/r1pro_pick_up_radio.yaml \
    --model "google/gemini-3.1-pro-preview"

# Interactive Web UI
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/cube_stack/franka_robosuite_cube_stack.yaml \
    --web-ui True
# Open http://localhost:8200

# Regression tests
./scripts/regression_test.sh quick    # 10-trial smoke test (~30s)
./scripts/regression_test.sh test1    # Full single-turn (~3 min)
```

> **Tip (BEHAVIOR):** Isaac Sim uses `OMNIGIBSON_GPU_ID` (not `CUDA_VISIBLE_DEVICES`) to select the GPU. For best performance on multi-GPU systems, run perception servers on a separate GPU (e.g. `OMNIGIBSON_GPU_ID=0` for the eval, and pre-launch SAM3/GraspNet with `CUDA_VISIBLE_DEVICES=1`). Set `OMNI_KIT_ACCEPT_EULA=YES` and `OMNIGIBSON_HEADLESS=1` for headless evaluation.

---

## Documentation

| Guide | Contents |
| ----- | -------- |
| [Adding Environments](docs/adding-environments.md) | Creating simulators, task environments, YAML configs |
| [Adding APIs](docs/adding-apis.md) | Implementing and registering new robot control APIs |
| [Configuration](docs/configuration.md) | YAML format, CLI flags, LLM provider setup |
| [LIBERO-PRO Tasks](docs/libero-tasks.md) | Setup, running any of 130+ LIBERO tasks, suite reference |
| [BEHAVIOR Tasks](docs/behavior-tasks.md) | Setup, R1Pro tasks, expected baselines, environment variables |
| [Development](docs/development.md) | Testing, linting, LIBERO/GraspNet setup, checkpoints, known issues |
| [Real-World Franka Panda Bringup](docs/real-franka.md) | Bringup with robots_realtime, real-robot QuickStart |
| [RL Training](docs/rl-training.md) | CaP-RL with GRPO/VeRL, sim-to-real transfer |
| [Skill Library Compilation](scripts/skill_library_compilation/README.md) | Analyze eval outputs, compile reusable skill libraries |

</details>

## Citation

```bibtex
@article{fu2025capx,
  title     = {{CaP-X}: A Framework for Benchmarking and Improving Coding Agents for Robot Manipulation},
  author    = {Fu, Max and Yu, Justin and El-Refai, Karim and Kou, Ethan and Xue, Haoru and Huang, Huang and Xiao, Wenli and Wang, Guanzhi and Li, Fei-Fei and Shi, Guanya and Wu, Jiajun and Sastry, Shankar and Zhu, Yuke and Goldberg, Ken and Fan, Jim},
  journal   = {arXiv preprint arXiv:2603.22435},
  year      = {2025},
  url       = {https://arxiv.org/abs/2603.22435}
}
```

## License

This project is released under the [MIT License](LICENSE).
