# CaP-X-Tron2

CaP-X-Tron2 runs model-generated Python with the LimX DACH_TRON2A two-finger gripper in MuJoCo. It supports single-arm Cube Lift and Pick & Place.

[简体中文](README.md) · [Simulation guide](docs/tron2_bringup.en.md) · [Tools and frames](docs/tron2_architecture.en.md)

The [TRON2 web evaluation](docs/tron2_bringup.en.md#web-workflow) provides controls for the perception server, LLM proxy setup, and evaluation for Cube Lift and Pick & Place.

## Contents

- [Quick start](#quick-start)
- [Simulation results](#simulation-results)
- [Open the visual replay](#open-the-visual-replay)
- [Setup and evaluation](#setup-and-evaluation)
- [Upstream project](#upstream-project)

## Quick start

Install the TRON2 simulation dependencies and set `TRON2_MJCF_PATH`. Run from the repository root, with the first two steps in separate terminals. The Web UI's `/tron2` page also supports service checks and evaluation. [Runtime setup](docs/tron2_bringup.en.md#setup) · [Web evaluation](docs/tron2_bringup.en.md#web-workflow)

1. Start the TRON2 RGB-D perception service.

   ```bash
   python -m capx.serving.launch_tron2_rgbd_server --port 8121
   ```

2. Start an OpenAI-compatible LLM service. You can reuse an existing local service. The command below uses a model environment with vLLM installed. [Install vLLM](https://docs.vllm.ai/en/latest/getting_started/installation/)

   ```bash
   python -m capx.serving.vllm_server \
     --model Qwen/Qwen2.5-Coder-3B-Instruct \
     --revision 488639f1ff808d1d3d0ba301aef8c11461451ec5 \
     --host 127.0.0.1 --port 18086 --max-model-len 4096
   ```

3. Run one seed of Cube Lift recovery evaluation. Choose a new output path for reruns.

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

## Simulation results

On the current fixed mounting scene, Qwen with multi-turn text feedback achieved **20/20** on both tasks. With VDM, Cube Lift reached **20/20** and Pick & Place **11/20**. [Paired protocol and results](docs/tron2_benchmark.en.md#current-results)

The published results below precede the unified pedestal. The standard experiments used a 0.590 m gap, and the occlusion experiment used a separate temporary layout with a 0.450 m gap. [Scene and rerun details](docs/tron2_bringup.en.md#results)

The hand-written Cube Lift Oracle reran at **20/20** with Mock, MuJoCo ground-truth poses, and RGB-D. The actual Qwen2.5-Coder-3B-Instruct evaluation used the same 20 seeds for each condition.

| MuJoCo ground-truth configuration | Single turn | Multi-turn |
| --- | ---: | ---: |
| Original prompt | 0/20 | 0/20 |
| Explicit five-action sequence and script format | 20/20 | 20/20 |

The original program omitted the lift command after closing the gripper. With explicit actions, every trial succeeded on the first turn and raised the cube center by 11.95–11.97 cm. The table counts physical success in simulation. [Evaluation criteria and runtime](docs/tron2_bringup.en.md#results)

With a fixed +X shift, the ground-truth position, RGB-D text, and RGB-D text + SmolVLM arms all recovered from **0/20** on the first turn to **20/20**. In the paired +X and −Y evaluation, target-motion VDM identified **20/20** image directions correctly, and the text and text + VDM arms each recovered **20/20**. [Recovery results and commands](docs/tron2_recovery.en.md)

A separate layout with a **0.450 m mounting gap** added head-camera occlusion. Both arms recovered on all 20 new seeds, and VDM identified **20/20** directions correctly. [Occlusion results, commands, and mounting limits](docs/tron2_calibrated_occlusion.en.md)

## Open the visual replay

Complete the [runtime and robot model setup](docs/tron2_bringup.en.md#setup), then run this from the repository root. MuJoCo executes the validated model program. Press **R** to replay it.

```bash
MUJOCO_GL=glfw python -m capx.envs.replay_tron2_cube_lift
```

## Setup and evaluation

- [Install simulator dependencies and get the official robot model](docs/tron2_bringup.en.md#setup)
- [Run the hand-written Oracle](docs/tron2_bringup.en.md#oracle) and [rerun the single-turn and multi-turn model comparison](docs/tron2_bringup.en.md#model-eval)
- [Tools, frames, and task criteria](docs/tron2_architecture.en.md) · [Hardware integration guide in Chinese](docs/tron2_hardware.md)

## Upstream project

[CaP-X code and upstream environment setup](https://github.com/capgym/cap-x) · [CaP-X paper](https://arxiv.org/abs/2603.22435) · [MIT license](LICENSE)
