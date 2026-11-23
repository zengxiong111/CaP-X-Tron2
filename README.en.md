# CaP-X-Tron2

CaP-X-Tron2 runs model-generated Python with the LimX DACH_TRON2A two-finger gripper in MuJoCo. It supports single-arm Cube Lift and Pick & Place.

[简体中文](README.md) · [Simulation guide](docs/tron2_bringup.en.md) · [Tools and frames](docs/tron2_architecture.en.md)

## Contents

- [Simulation results](#simulation-results)
- [Open the visual replay](#open-the-visual-replay)
- [Setup and evaluation](#setup-and-evaluation)
- [Upstream project](#upstream-project)

## Simulation results

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
