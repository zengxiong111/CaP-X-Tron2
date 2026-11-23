# TRON2 Paired Benchmark

Run Cube Lift and Pick & Place in the shared MuJoCo mounting scene. The tabletop is at world Z = 0.620 m, `base_Link` is at world Z = 1.070 m, and the mounting gap is 0.450 m.

[简体中文](tron2_benchmark.md) · [Runtime setup](tron2_bringup.en.md#setup)

## Contents

- [Configuration](#configuration)
- [Run the benchmark](#run-the-benchmark)
- [Current results](#current-results)
- [Mapping to CaP-Bench](#mapping-to-cap-bench)

## Configuration

| Item | Setting |
| --- | --- |
| Scene | A simulated floor recess supports the vendor pedestal. The surrounding floor stays at world Z = 0. The tabletop and arm links retain their definitions. |
| Simulator runtime | Linux, Python 3.12.3, and MuJoCo 3.17.0. |
| Right gripper | The grasp yaw is increased by 15° from its previous value. |
| Task | `cube_lift_s2_guided.yaml` or `pick_place_s2_guided.yaml` |
| Model | Qwen2.5-Coder-3B-Instruct via a local Transformers endpoint, with BF16 greedy decoding. [Weights revision](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| Perception | Head RGB-D with overview fallback when the estimate is unavailable. All conditions use the same pose service and camera extrinsics. |
| Disturbance | After the first successful right-arm approach, shift the cube 75 mm along +X for odd seeds and −Y for even seeds. |
| Scoring | Cube Lift checks stable grasp and lift. Pick & Place checks target error and stability after release. |

Across the two disturbed tasks on seeds 41–44, the minimum right wrist joint-limit margin was 0.04610 rad on the first turn and 0.13373 rad during Oracle recovery. The pedestal's geometric fit to the support plate, the pose, and the joint margins were checked in simulation. The physical mount and its safety margins still need hardware measurements.

## Run the benchmark

Follow the [Quick start](../README.en.md#quick-start) to prepare the model and perception servers. Set `MUJOCO_GL=egl`, `CAPX_MODEL_NAME`, and `CAPX_MODEL_URL` in the simulator environment, then run from the repository root. Set `benchmark_task` to `pick_place_s2_guided` for the other task. Use a fresh output directory for reruns.


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

JSON records per-seed results, first-turn program and physics digests, frame hashes, and recovery outcomes. The three model conditions share each task's first-turn program. The VDM arm reads the text arm's first-turn record and verifies pairing. Use `--perturbation none` to measure ordinary task completion without the controlled shift.

The occlusion comparison runs the text and VDM arms. Replace the module in those two commands with `capx.envs.evaluate_tron2_calibrated_occlusion`, use `--trials 4`, and choose a different output directory. The other parameters stay the same.

## Current results

### Unoccluded head camera

Both tasks were evaluated on seeds 41–60. The table counts final successes after the disturbance. For each seed, the three model conditions had identical first-turn programs, physics states, and RGB frames. All first turns missed their grasp. The hand-written Oracle used the same disturbances and seeds.

| Task | Two-turn Oracle | Single-turn Qwen | Qwen with text feedback | Qwen with text + VDM | Correct VDM directions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cube Lift | 20/20 | 0/20 | 20/20 | 20/20 | 20/20 |
| Pick & Place | 20/20 | 0/20 | 20/20 | 11/20 | 20/20 |

All nine Pick & Place failures in the VDM arm reused the pre-lift TCP, and the direction estimate was correct in all nine. A diagnostic replay changed one line in each of those nine programs to read the TCP after lifting the cube. All nine then succeeded. The table retains the original model-generated results. Seed 60 in that arm ran in a separate process with the same baseline, and its first-turn state and frame hashes matched.

### Partial head-camera occlusion

Reran seeds 41–44. VDM uses the head camera's RGB frames. The object pose tool can fall back to the overview camera.

| Task | Multi-turn text | Text + VDM | Correct VDM directions | VDM unavailable |
| --- | ---: | ---: | ---: | ---: |
| Cube Lift | 4/4 | 4/4 | 3/4 | 1/4 |
| Pick & Place | 4/4 | 3/4 | 2/4 | 2/4 |

Only 3–6 red pixels remained in the later frame when VDM was unavailable. For Pick & Place seed 43, VDM identified the correct direction, but the recovery program reused the pre-lift TCP and did not place the cube. These four seeds cover this occlusion setting.

## Mapping to CaP-Bench

This table compares interfaces. Tasks, prompts, and trial counts follow the TRON2 protocol. [CaP-Bench tier definitions](https://arxiv.org/html/2603.22435v1#S3)

| Upstream tier | TRON2 coverage |
| --- | --- |
| S1 | Ground-truth poses, high-level tools, and one program execution |
| S2 | RGB-D poses, high-level tools, and one program execution |
| S3, S4 | Low-level vision and control primitives remain pending |
| M1 | Multi-turn text recovery on the same simulator state |
| M2 | Unified validation of raw RGB input across turns remains pending |
| M3 | A partial comparison using target-motion VDM. The upstream tier also expects VLM scene descriptions and task completion judgments |
| M4 | Combining low-level primitives with VDM remains pending |
