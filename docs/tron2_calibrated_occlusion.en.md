# TRON2 Cube Lift Occlusion at a Fixed Mounting Gap

This evaluation compares text feedback with text plus target-motion VDM at tabletop world Z = 0.620 m and a 0.450 m gap from the tabletop to the simulated `base_Link`. Results were recorded on 2026-11-23.

These results use the previous mounting overlay. To reproduce the historical numbers, use commit `62c243a` in a separate worktree. The same evaluation entry point now uses the recessed mount and the revised right gripper orientation. [Current paired benchmark](tron2_benchmark.en.md)

[简体中文](tron2_calibrated_occlusion.md) · [Simulation environment and official assets](tron2_bringup.en.md#setup)

## Contents

- [Setup and scope](#setup-and-scope)
- [Evaluation results](#evaluation-results)
- [Rerun steps](#rerun-steps)

## Setup and scope

| Item | Setting |
| --- | --- |
| Scene | Official DACH_TRON2A two-finger gripper. The experiment entry point moves `base_Link` from world Z = 1.210 m to 1.070 m in a temporary MJCF. The tabletop stays at 0.620 m. [Official asset revision](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71) |
| Trajectory and perception | A new right-arm ready branch targets TCP `[0.430, -0.220, -0.320]` m in base coordinates. The RGB-D crop shifts in base coordinates so its world bounds stay fixed. |
| Disturbance | Seeds 41–60, with a 75 mm shift along +X on odd seeds and −Y on even seeds. |
| Occlusion | Three fixed image regions cover head RGB and invalidate the corresponding depth. The unoccluded overview camera remains available for RGB-D pose fallback. |
| Code model | Qwen2.5-Coder-3B-Instruct, BF16 greedy decoding. [Weights revision](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |

In this experiment layout, the vendor pedestal's `base_3_Link` mesh intersects the floor at world Z = 0 by about **13.0 cm**. Evaluation covers Cube Lift recovery for the simulated arm. The complete scene still requires a compatible pedestal, and the physical mounting datum still requires calibration.

## Evaluation results

At the 0.450 m gap, the original ready posture failed its first approach with IK errors for both the S1 and S2 Oracles on seeds 21–24. With the new ready posture and RGB-D crop, S2 succeeded **4/4** on the first turn without a disturbance and recovered **4/4** on the second turn across the two disturbance directions. The Oracle preflight measured a minimum arm joint-limit margin of about 0.00045 rad.

| Metric | Text feedback | Text + VDM |
| --- | ---: | ---: |
| First-turn empty grasps | 20/20 | 20/20 |
| Successful recoveries | 20/20 | 20/20 |
| Seeds using overview during recovery | 12/20 | 12/20 |
| Correct movement directions | — | 20/20 |

The executed action sequences matched in 20/20 pairs, and 13/20 recovery programs were identical. This evaluation measured no recovery-rate gain. Median red-pixel occlusion was 59.3% before the first turn and 54.5% after it. Both frames in 14/20 pairs had at least 25% red-pixel occlusion.

First-turn physics and depth frames matched by seed. The recovery prompts differed only by the VDM description. Rerendering 24 of the 40 RGB snapshots changed up to six pixels per frame by at most one level per channel. After checking that both red classification masks matched, VDM used the verified text baseline snapshots for these frames.

## Rerun steps

1. Set up the simulation environment and official assets as described in the bring-up guide. Point `TRON2_MJCF_PATH` to the original `robot_grasper.xml`, set `CAPX_MODEL_URL` to the full OpenAI-compatible Chat Completions endpoint, and set `CAPX_MODEL_NAME` to the model ID accepted by the endpoint. Run from the repository root. [Setup instructions](tron2_bringup.en.md#setup)
2. Run the text feedback arm first.

   ```bash
   export MUJOCO_GL=egl
   recovery_options=(
     --config env_configs/tron2/cube_lift_s1_guided_multi.yaml
     --model "$CAPX_MODEL_NAME" --server-url "$CAPX_MODEL_URL"
     --start-seed 41 --trials 20 --offset-directions '+X,-Y'
   )
   python -m capx.envs.evaluate_tron2_calibrated_occlusion "${recovery_options[@]}" \
     --output outputs/tron2_calibrated_occlusion/text.json
   ```

3. Run the paired VDM arm in the same shell. Keep both `text.json` and `text_frames/` from the text arm for matching. Use a new output directory for each run. The console prints success counts and the JSON includes head-camera occlusion statistics, pose camera calls, and RGB snapshot replay records. For a smoke test, replace `--trials 20` with `--trials 2`.

   ```bash
   python -m capx.envs.evaluate_tron2_calibrated_occlusion "${recovery_options[@]}" \
     --baseline outputs/tron2_calibrated_occlusion/text.json --target-motion \
     --output outputs/tron2_calibrated_occlusion/vdm.json
   ```
