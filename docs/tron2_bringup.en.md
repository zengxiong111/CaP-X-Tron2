# Running and validating TRON2 simulation

Use MuJoCo to replay Cube Lift, run the hand-written Oracle, and compare a live coding model in single-turn and multi-turn settings. Run the commands from the repository root.

[简体中文](tron2_bringup.md) · [Tools and frames](tron2_architecture.en.md)

## Contents

- [Runtime and official model](#setup)
- [MuJoCo visual replay](#replay)
- [Oracle baseline](#oracle)
- [Live model comparison](#model-eval)
- [Validation results](#results)

<a id="setup"></a>

## Runtime and official model

1. Create a dedicated Python 3.10–3.12 environment. Install the TRON2 simulation dependencies.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements-tron2.txt
   ```

2. Store the official DACH_TRON2A model and meshes beside the repository. For Mock, proceed directly to the [Oracle baseline](#oracle). [LimX model and license](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71)

   ```bash
   git clone --filter=blob:none --no-checkout \
     https://github.com/limxdynamics/tron2-robot-description.git ../tron2-robot-description
   git -C ../tron2-robot-description sparse-checkout set --no-cone \
     '/LICENSE' '/tron2a/DACH_TRON2A/xml/robot_grasper.xml' '/tron2a/DACH_TRON2A/meshes/'
   git -C ../tron2-robot-description checkout --detach 9939c22e69d27653ec0ba8a505859a2903dd1a71
   export TRON2_MJCF_PATH="$PWD/../tron2-robot-description/tron2a/DACH_TRON2A/xml/robot_grasper.xml"
   ```

<a id="replay"></a>

## MuJoCo visual replay

On a Linux desktop with MuJoCo 3.17.0, replay the validated seed 1. The viewer executes the saved model program and displays the physical verdict and lift height. Press **R** to replay. [Model-generated program](../capx/envs/assets/tron2_tasks/cube_lift_qwen.txt)

```bash
MUJOCO_GL=glfw python -m capx.envs.replay_tron2_cube_lift
```

<a id="oracle"></a>

## Oracle baseline

The three Cube Lift configurations use Mock, simulation ground-truth poses, and RGB-D estimates. S2 needs a working rendering backend. The Linux launcher defaults to EGL. For Pick & Place, replace `cube_lift` with `pick_place` in the config name.

```bash
for mode in mock s1 s2; do
  python -m capx.envs.launch \
    --config-path "env_configs/tron2/cube_lift_${mode}.yaml" \
    --use-oracle-code True --total-trials 20
done
```

Use `TRON2_TEST_RENDER=1 python -m pytest -q tests/tron2` to run the regression checks including RGB-D. Install `pytest` and set `TRON2_MJCF_PATH` first.

<a id="model-eval"></a>

## Live model comparison

Connect to a running OpenAI-compatible Chat Completions endpoint. `CAPX_MODEL_URL` is the full endpoint URL and `CAPX_MODEL_NAME` is the model ID it accepts. This evaluation used local Qwen2.5-Coder-3B-Instruct with BF16 greedy decoding. [Pinned model weights](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) · [Endpoint configuration](configuration.md#adding-new-llm-providers)

```bash
for config in cube_lift_s1_single cube_lift_s1 cube_lift_s1_guided_single cube_lift_s1_guided_multi; do
  python -m capx.envs.launch \
    --config-path "env_configs/tron2/${config}.yaml" \
    --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
    --temperature 0 --max-tokens 768 --total-trials 20
done
```

All four configurations use seeds 1–20 and simulation ground-truth poses. For each prompt, both arms share the initial prompt and action budget. A single-turn trial allows one code execution and a multi-turn trial allows up to six. `Task completed` in `summaries.txt` counts physical successes. `all_responses.json` records generations and retries.

<a id="results"></a>

## Validation results

| Evaluation | Result |
| --- | --- |
| Cube Lift Oracle rerun | Mock, MuJoCo S1, and MuJoCo S2 each achieved 20/20 |
| Original prompt | Both turn settings achieved 0/20. The program omitted the lift after closing the gripper, and each multi-turn trial used five regenerations. |
| Explicit five-action sequence and script format | Both turn settings achieved 20/20 on the first turn. The cube center rose by 11.95–11.97 cm. |
| TRON2 regressions | 8 passed, including S2 with an injected MuJoCo backend |

Cube Lift requires a held cube to rise at least 7 cm and stay at or below 0.04 m/s during a 0.25-second stability window. Validation used source `ce2e708228badee5ba601ebcc03f6aaa069d33cf`, Linux, Python 3.12.3, MuJoCo 3.17.0, and tabletop world Z of 0.620 m. The published replay program has SHA-256 `2d7ad6a562b64e03d9179b0980c122044cdf6b783bf6a70f842553ca47531881`.

The repository previously recorded Pick & Place Oracle results of 20/20 under all three configurations. Live model validation covers Cube Lift with ground-truth poses and RGB-D recovery. The viewer executes the saved program. [Perturbation and VDM evaluation](tron2_recovery.en.md)
