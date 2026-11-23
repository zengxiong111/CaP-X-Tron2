# TRON2 Cube Lift Recovery Evaluation

This page records the ground-truth recovery and RGB-D visual differencing (VDM) comparisons completed on 2026-11-23 and gives the RGB-D rerun commands.

[简体中文](tron2_recovery.md) · [Simulation environment and official assets](tron2_bringup.en.md#setup)

## Contents

- [Results](#results)
- [Experiment setup](#experiment-setup)
- [Rerun the RGB-D comparison](#rerun-the-rgb-d-comparison)

## Results

| Object position and second-turn feedback | First-turn physical success | Successful recovery after empty grasp |
| --- | ---: | ---: |
| Ground-truth position + text | 0/20 | 20/20 |
| RGB-D + text | 0/20 | 20/20 |
| RGB-D + text and VDM | 0/20 | 20/20 |

Both RGB-D arms raised the cube center by **11.94–12.00 cm**. First-turn code, simulation state, and before/after frame hashes matched for every seed. The red cube moved about **27–28 px** upward in the images. All 20 SmolVLM descriptions missed the movement. Physical success requires maintaining the grasp, raising the cube center by at least 7 cm, and staying at or below 0.04 m/s during a 0.25-second stability window. [Task scoring](tron2_bringup.en.md#results)

## Experiment setup

| Item | Setting |
| --- | --- |
| Scene | Official DACH_TRON2A two-finger gripper, tabletop world Z of 0.620 m |
| Disturbance | Shift the cube by 0.075 m along positive world X after the first approach. Simulation contacts determine whether the grasp is empty. |
| Pairing | Seeds 1–20. The second turn continues from the first turn's terminal state. Adding VDM text is the sole change in the RGB-D comparison. |
| Code model | Qwen2.5-Coder-3B-Instruct, BF16 greedy decoding. [Weights revision](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| Vision model | SmolVLM-500M-Instruct receives two RGB snapshots from the head camera. [Weights revision](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/tree/753c1752602b5e739af7a7fa6947a635051897a3) |

## Rerun the RGB-D comparison

The commands below cover both RGB-D arms. The ground-truth row records an earlier baseline with the same disturbance. Complete the [simulation setup](tron2_bringup.en.md#setup) and run from the repository root. Set `CAPX_MODEL_URL` and `CAPX_VDM_URL` to the full URLs of two OpenAI-compatible Chat Completions endpoints. Set `CAPX_MODEL_NAME` and `CAPX_VDM_NAME` to the model IDs accepted by those endpoints. Add `--trials 1` to both commands for a single-seed smoke test. The default is 20 trials per arm. Choose a new output path for each run.

```bash
export MUJOCO_GL=egl
config=env_configs/tron2/cube_lift_s1_guided_multi.yaml
python -m capx.envs.evaluate_tron2_recovery \
  --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
  --output outputs/tron2_recovery/text.json
python -m capx.envs.evaluate_tron2_recovery \
  --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
  --baseline outputs/tron2_recovery/text.json \
  --vdm-server-url "$CAPX_VDM_URL" --vdm-model "$CAPX_VDM_NAME" \
  --output outputs/tron2_recovery/vdm.json
```

The config supplies shared action guidance. The recovery entry point uses **S2 RGB-D** to locate the object. The second command reuses the first program and checks the simulator state and images before recovery for each seed. The JSON output's `summary` records physical successes and `seed_results` records actions, model responses, and VDM descriptions.
