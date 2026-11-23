# TRON2 Cube Lift Recovery Evaluation

This page records the TRON2 Cube Lift recovery experiments completed on 2026-11-23, covering ground-truth pose, paired RGB-D recovery, and red cube motion detection.

These runs used the vendor MJCF's original base layout, with the tabletop at world Z = 0.620 m and `base_Link` at world Z = 1.210 m. [Follow-up occlusion evaluation at a 0.450 m mounting gap](tron2_calibrated_occlusion.en.md)

[简体中文](tron2_recovery.md) · [Simulation environment and official assets](tron2_bringup.en.md#setup)

## Contents

- [Results](#results)
  - [Fixed +X shift](#fixed-x-shift)
  - [Red cube motion detection](#red-cube-motion-detection)
  - [Paired recovery in two directions](#paired-recovery-in-two-directions)
- [Experiment setup](#experiment-setup)
- [Rerun the RGB-D comparison](#rerun-the-rgb-d-comparison)
  - [Fixed direction with SmolVLM](#fixed-direction-with-smolvlm)
  - [Two directions with target tracking](#two-directions-with-target-tracking)

## Results

### Fixed +X shift

| Object position and second-turn feedback | First-turn physical success | Successful recovery after empty grasp |
| --- | ---: | ---: |
| Ground-truth position + text | 0/20 | 20/20 |
| RGB-D + text | 0/20 | 20/20 |
| RGB-D + text and VDM | 0/20 | 20/20 |

Both RGB-D arms raised the cube center by **11.94–12.00 cm**. First-turn code, simulation state, and before/after frame hashes matched for every seed. The red cube moved about **27–28 px** upward in the images. All 20 SmolVLM descriptions missed the movement. Physical success requires maintaining the grasp, raising the cube center by at least 7 cm, and staying at or below 0.04 m/s during a 0.25-second stability window. [Task scoring](tron2_bringup.en.md#results)

### Red cube motion detection

Target-motion VDM extracts saturated red pixels from each RGB image and uses a trimmed centroid to estimate displacement, with a 3 px motion threshold.

| Archived images and derived controls | Expected class | Target tracking |
| --- | --- | ---: |
| 20 original pairs | Up | 20/20 |
| 20 reversed pairs | Down | 20/20 |
| 20 identical pairs | Unchanged | 20/20 |
| 20 pairs with the red target missing | Unavailable | 20/20 |

The SmolVLM prompt pilot returned `LEFT` on all original, reversed, and identical pairs, for **0/60** correct classifications.

### Paired recovery in two directions

Qwen used seeds 21–40. The disturbance shifted the cube by 75 mm along +X for 10 seeds and −Y for 10 seeds. Initial code, first-turn simulation state, and before/after RGB frame hashes matched for every seed.

| Metric | Text feedback | Text + target-motion VDM |
| --- | ---: | ---: |
| First-turn empty grasps | 20/20 | 20/20 |
| Successful recoveries after empty grasps | 20/20 | 20/20 |
| Correct image directions | — | 20/20 |

In the head camera, +X appeared upward and −Y appeared rightward, with 10/10 correct in each direction. Direction scoring used an offline projection of the simulated cube center. The code model received only the visual estimate. All 20 recovery pairs agreed. The four-direction preflight encountered IK or tracking failures at both 75 mm and 55 mm, so this evaluation used the two directions that passed the Oracle preflight. The missing-red control was an offline detection test. Paired recovery did not cover partial occlusion.

## Experiment setup

| Item | Setting |
| --- | --- |
| Scene | Official DACH_TRON2A two-finger gripper, tabletop world Z of 0.620 m |
| Disturbance | Shift the cube by 0.075 m in the world XY plane after the first approach. Simulation contacts determine whether the grasp is empty. |
| Pairing | Seeds 1–20 for the fixed direction and 21–40 for the two directions. The second turn continues from the first turn's terminal state. Adding VDM text is the sole change in the RGB-D comparison. |
| Code model | Qwen2.5-Coder-3B-Instruct, BF16 greedy decoding. [Weights revision](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| Vision model | SmolVLM-500M-Instruct receives two RGB snapshots from the head camera. [Weights revision](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/tree/753c1752602b5e739af7a7fa6947a635051897a3) |

## Rerun the RGB-D comparison

### Fixed direction with SmolVLM

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

### Two directions with target tracking

Use the same simulation environment and code-model endpoint. The local target tracker reads only two RGB images. Both commands run seeds 21–40, shifting along +X on odd seeds and −Y on even seeds.

1. Run the text feedback arm to generate the matched baseline.

   ```bash
   export MUJOCO_GL=egl
   config=env_configs/tron2/cube_lift_s1_guided_multi.yaml
   python -m capx.envs.evaluate_tron2_recovery \
     --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
     --start-seed 21 --offset-directions '+X,-Y' \
     --output outputs/tron2_target_motion/text.json
   ```

2. Run the target-tracking arm in the same shell. The output includes pixel displacement and the offline direction check for each seed, plus the summary field `correct_visual_directions`.

   ```bash
   python -m capx.envs.evaluate_tron2_recovery \
     --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
     --start-seed 21 --offset-directions '+X,-Y' \
     --baseline outputs/tron2_target_motion/text.json --target-motion \
     --output outputs/tron2_target_motion/vdm.json
   ```
