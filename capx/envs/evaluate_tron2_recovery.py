"""Compare two-turn Cube Lift recovery with RGB-D and optional visual differencing."""

import argparse
import base64
import hashlib
import json
import os
import signal
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from time import monotonic

import numpy as np
from PIL import Image

from capx.envs.configs.loader import DictLoader
from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.envs.tasks.base import CodeExecEnvConfig
from capx.envs.tasks.tron2.cube_lift import Tron2CubeLiftCodeEnv
from capx.envs.tasks.tron2.pick_place import Tron2PickPlaceCodeEnv
from capx.envs.trial import _get_visual_differencing_feedback
from capx.integrations.tron2.recovery_backend import RecoveryMujocoBackend
from capx.integrations.tron2.mounting import BASE_WORLD_Z, MOUNT_GAP, TABLETOP_Z
from capx.integrations.tron2.target_motion import describe_target_motion
from capx.llm.client import ModelQueryArgs, query_model
from capx.utils.launch_utils import _extract_code


class NoDisturbanceRecoveryBackend(RecoveryMujocoBackend):
    """Keep the recovery backend's replay digest while disabling its object shift."""

    def reset(self, seed=None):
        super().reset(seed)
        self._offset_xy = (0.0, 0.0)


def generate(args, messages):
    started = monotonic()
    response = query_model(args, messages)
    (program,) = _extract_code(response["content"])
    return {
        "messages": messages,
        "raw_response": response["content"],
        "program": program,
        "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
        "request_seconds": monotonic() - started,
    }


def interrupt_script(_signum, _frame):
    raise TimeoutError("Generated Python reached the 15-second execution limit")


def execute(env, backend, generation):
    low_level = env.low_level_env
    step_offset = low_level.episode_info()["steps"]
    pose_calls = low_level.pose_estimate_calls
    old_handler = signal.signal(signal.SIGALRM, interrupt_script)
    signal.setitimer(signal.ITIMER_REAL, 15)
    try:
        observation, reward, terminated, truncated, info = env.step(generation["program"])
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    if not low_level.privileged:
        assert "object_poses" not in observation, "unexpected privileged observation"
    robot = observation["robot_state"]
    return {
        "task_completed": info["task_completed"],
        "reward": reward,
        "terminated": terminated,
        "truncated": truncated,
        "sandbox_rc": info["sandbox_rc"],
        "pose_api_calls": low_level.pose_estimate_calls - pose_calls,
        "failure_reason": info["failure_reason"],
        "actions": [entry for entry in info["action_history"] if entry["step"] > step_offset],
        "physical_cube_pose_after": backend.task_state().cube_pose,
        "grasped_by_after": robot["grasped_by"],
        "right_tcp": robot["tcp_poses"]["right"],
        "sim_seconds": info["elapsed_seconds"],
        "stdout": info["stdout"],
        "stderr": info["stderr"],
        "generation": generation,
    }


def first_state_sha256(backend, turn):
    digest = hashlib.sha256(backend.physics_state_bytes())
    digest.update(json.dumps(turn["actions"], sort_keys=True).encode())
    return digest.hexdigest()


def encode_rgb(frame):
    with BytesIO() as stream:
        Image.fromarray(frame["rgb"]).save(stream, format="PNG")
        return stream.getvalue()


def encode_rgb_unpatched(frame):
    """Encode an auxiliary view without calling wrappers that audit head frames."""
    with BytesIO() as stream:
        Image.fromarray(frame["rgb"]).save(stream, format="PNG")
        return stream.getvalue()


def project_cube_center(frame, cube_pose):
    # Use the physical cube only to score the image-based direction.
    transform = frame["T_base_camera"]
    position = transform[:3, :3].T @ (np.asarray(cube_pose[:3]) - transform[:3, 3])
    pixels = frame["K"] @ position
    return pixels[:2] / pixels[2] if pixels[2] > 0 else None


def recovery_prompt(first, task_prompt, visual_diff=None, task="cube_lift"):
    feedback = {
        "failure_reason": first["failure_reason"],
        "failed_actions": [action for action in first["actions"] if not action["success"]],
        "grasped_by": first["grasped_by_after"],
        "right_tcp": first["right_tcp"],
    }
    if task == "cube_lift":
        recovery_instruction = (
            "Start the recovery program by reading the new cube pose using get_object_pose. "
            "Use the current cube coordinates for every action, because the original grasp "
            "coordinates are stale. The right gripper is not holding the cube in an empty "
            "grasp. Open it, approach above the current cube, descend, close, and lift. "
            "The procedure below refers to the pose at the start of this recovery program.\n"
        )
    else:
        recovery_instruction = (
            'Read the current cube pose with get_object_pose("cube") and the target pose '
            'with get_object_pose("target"). Continue from the current state and finish '
            "the Pick & Place objective below.\n"
        )
    content = (
        "The first program just ran. Continue from its resulting state in the same "
        "episode. Simulator feedback: " + json.dumps(feedback) + "\n"
        + recovery_instruction + task_prompt
    )
    if visual_diff is not None:
        content += "\nVisual difference from two RGB snapshots: " + visual_diff
    return [
        {"role": "system", "content": "You generate executable Python for a robot simulator."},
        {"role": "user", "content": content},
    ]


def describe_change(args, before, after, task="cube_lift"):
    images = [
        "data:image/png;base64," + base64.b64encode(frame).decode() for frame in (before, after)
    ]
    start = monotonic()
    description = _get_visual_differencing_feedback(
        args,
        "Lift the red cube and hold it in the right gripper."
        if task == "cube_lift"
        else "Pick up the cube and place it on the marked target region.",
        images,
    )
    elapsed = monotonic() - start
    if not description or not description.strip():
        raise RuntimeError("The VLM returned an empty visual difference")
    return {"text": description.strip(), "request_seconds": elapsed}


def measure_target_motion(before, after, before_pixel, after_pixel):
    start = monotonic()
    difference = describe_target_motion(before, after)
    difference["request_seconds"] = monotonic() - start
    if before_pixel is None or after_pixel is None:
        return difference

    reference = after_pixel - before_pixel
    observed = difference["delta_px"]
    direction_match = False
    if difference["status"] == "moved":
        axis = int(np.argmax(np.abs(reference)))
        direction_match = bool(
            np.argmax(np.abs(observed)) == axis and observed[axis] * reference[axis] > 0
        )
    difference["offline_projected_delta_px"] = reference.tolist()
    difference["direction_match"] = direction_match
    return difference


def write_report(report, output):
    temporary = output.with_name(output.name + ".partial")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


def task_from_config(config):
    task = config["low_level"].get("task", "cube_lift")
    if task not in ("cube_lift", "pick_place"):
        raise ValueError(f"Unsupported TRON2 task in config: {task}")
    return task


def offset_profile(legacy_directions, perturbation):
    if perturbation == "cube_shift:+X":
        return "+X"
    if perturbation == "cube_shift:alternating":
        return "+X,-Y"
    if perturbation == "none":
        return "none"
    return legacy_directions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--single-turn", action="store_true", help="Stop after the first physical program")
    parser.add_argument("--oracle", action="store_true", help="Run task Oracle code without a model request")
    parser.add_argument("--perception-url", help="Override configured pose service URL")
    parser.add_argument("--record-overview", action="store_true", help="Also save an overview frame")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument(
        "--offset-directions",
        choices=("+X", "+X,-Y"),
        default="+X",
        help="Use +X for all seeds or alternate +X on odd seeds and -Y on even seeds",
    )
    parser.add_argument(
        "--perturbation",
        choices=("cube_shift:+X", "cube_shift:alternating", "none"),
        help="Explicit controlled disturbance profile; legacy offset flags remain supported",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3.5-27B-AWQ")
    parser.add_argument("--server-url", default="http://127.0.0.1:8110/chat/completions")
    parser.add_argument(
        "--fail-fast-model", action="store_true",
        help="Report model server errors without the batch evaluator's retry delay",
    )
    parser.add_argument("--camera", choices=("head", "overview"), default="head")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--target-motion",
        action="store_true",
        help="Use a local red-target tracker for the paired VDM arm",
    )
    parser.add_argument("--vdm-model")
    parser.add_argument("--vdm-server-url")
    options = parser.parse_args(argv)
    if options.start_seed < 1 or options.trials < 1 or options.output.exists():
        parser.error("Use a positive start seed and trial count and a new output path")
    learned_vdm = bool(options.vdm_model or options.vdm_server_url)
    if learned_vdm and (not options.vdm_model or not options.vdm_server_url):
        parser.error("Learned VDM requires both --vdm-model and --vdm-server-url")
    if learned_vdm and options.target_motion:
        parser.error("Choose either --target-motion or a learned VDM endpoint")
    paired = options.target_motion or learned_vdm
    if paired != bool(options.baseline):
        parser.error("--baseline and one VDM method must be specified together")
    if options.oracle and paired:
        parser.error("Oracle runs cannot be paired as model-generated text baselines")
    seeds = range(options.start_seed, options.start_seed + options.trials)

    loaded = DictLoader.load(str(options.config))
    config = loaded["env"]["cfg"]
    try:
        task = task_from_config(config)
    except ValueError as error:
        parser.error(str(error))
    offset_directions = offset_profile(options.offset_directions, options.perturbation)
    vendor_model = os.environ.get("TRON2_MJCF_PATH")
    vendor_sha256 = hashlib.sha256(Path(vendor_model).read_bytes()).hexdigest() if vendor_model else None
    scene = {
        "tabletop_world_z_m": TABLETOP_Z,
        "base_link_world_z_m": BASE_WORLD_Z,
        "tabletop_to_base_gap_m": MOUNT_GAP,
        "fixture_id": "tron2_fixed_gap_0p620_0p450_v1",
        "vendor_mjcf_sha256": vendor_sha256,
    }
    args = ModelQueryArgs(
        model=options.model,
        server_url=options.server_url,
        temperature=0,
        max_tokens=768,
        max_server_retries=0 if options.fail_fast_model else None,
        request_timeout=45 if options.fail_fast_model else 200,
        use_configured_url=options.fail_fast_model,
    )
    baseline_rows = {}
    first_generation = None
    vlm_args = None
    if paired:
        baseline = json.loads(options.baseline.read_text(encoding="utf-8"))
        if (
            baseline["variant"] != "text"
            or baseline["camera"] != options.camera
            or baseline["model"] != options.model
            or baseline.get("offset_directions", "+X") != offset_directions
            or (baseline.get("scene") is not None and baseline["scene"] != scene)
        ):
            parser.error(
                "The text baseline must use the same camera, code model, and offset directions"
            )
        baseline_rows = {row["seed"]: row for row in baseline["seed_results"]}
        if set(seeds) - baseline_rows.keys():
            parser.error("The baseline must contain every requested trial seed")
        first_generation = baseline_rows[options.start_seed]["initial"]["generation"]
    if learned_vdm:
        vlm_args = ModelQueryArgs(
            model=options.vdm_model,
            server_url=options.vdm_server_url,
            temperature=0,
            max_tokens=96,
        )

    snapshots = options.output.parent / (options.output.stem + "_frames")
    snapshots.mkdir(parents=True)
    backend_type = NoDisturbanceRecoveryBackend if offset_directions == "none" else RecoveryMujocoBackend
    backend = backend_type(alternate_offsets=offset_directions == "+X,-Y")
    privileged = bool(config["low_level"].get("privileged", False))
    visual_pose = bool(config["low_level"].get("visual_pose", not privileged))
    perception_url = options.perception_url or config["low_level"].get("perception_url")
    perception_timeout = float(config["low_level"].get("perception_timeout_s", 5.0))
    runtime = {
        "simulator": "mujoco",
        "backend": "NoDisturbanceRecoveryBackend" if offset_directions == "none" else "RecoveryMujocoBackend",
        "pose_mode": "privileged" if privileged else "remote_rgbd" if perception_url else "local_rgbd",
        "perception_url": perception_url,
        "perception_timeout_s": perception_timeout,
        "max_attempts": 2,
        "camera": options.camera,
    }
    low_level = Tron2MujocoEnv(
        backend=backend,
        task=task,
        enable_render=True,
        privileged=privileged,
        visual_pose=visual_pose,
        perception_url=perception_url,
        perception_timeout_s=perception_timeout,
        max_attempts=2,
    )
    env_type = Tron2CubeLiftCodeEnv if task == "cube_lift" else Tron2PickPlaceCodeEnv
    env = env_type(
        CodeExecEnvConfig(
            low_level=low_level,
            apis=config["apis"],
            prompt=config.get("prompt"),
        )
    )
    report = {
        "format_version": 2,
        "task": task,
        "variant": "vdm" if paired else "text",
        "vdm_method": "target_motion"
        if options.target_motion
        else "learned"
        if learned_vdm
        else None,
        "model": args.model,
        "camera": options.camera,
        "offset_directions": offset_directions,
        "perturbation": options.perturbation or ("cube_shift:alternating" if offset_directions == "+X,-Y" else "none" if offset_directions == "none" else "cube_shift:+X"),
        "single_turn": options.single_turn,
        "oracle": options.oracle,
        "privileged": privileged,
        "scene": scene,
        "runtime": runtime,
        "vlm_model": options.vdm_model,
        "seed_results": [],
    }
    from capx.envs.runner import _start_api_servers, _stop_api_servers

    server_configs = None if options.perception_url else loaded.get("api_servers")
    server_procs = _start_api_servers(server_configs)
    try:
        for seed in seeds:
            obs, _ = env.reset(seed=seed, options={"trial": seed})
            if not privileged:
                assert "object_poses" not in obs, "unexpected privileged initial observation"
            initial_messages = deepcopy(obs["full_prompt"])
            if first_generation is None:
                if options.oracle:
                    program = env.oracle_code
                    first_generation = {
                        "messages": initial_messages,
                        "raw_response": program,
                        "program": program,
                        "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
                        "request_seconds": 0.0,
                    }
                else:
                    first_generation = generate(args, initial_messages)
            if initial_messages != first_generation["messages"]:
                raise RuntimeError("Initial model prompt changed")
            initial_pose = backend.task_state().cube_pose
            before_frame = low_level.get_image(options.camera)
            before = encode_rgb(before_frame)
            initial = execute(env, backend, first_generation)
            initial["disturbance"] = deepcopy(backend.disturbance)
            first_key = first_state_sha256(backend, initial)
            after_frame = low_level.get_image(options.camera)
            after = encode_rgb(after_frame)
            before_sha = hashlib.sha256(before).hexdigest()
            after_sha = hashlib.sha256(after).hexdigest()
            if paired:
                baseline_row = baseline_rows[seed]
                expected = (baseline_row["first_state_sha256"], *baseline_row["frame_sha256"])
                if (first_key, before_sha, after_sha) != expected:
                    raise RuntimeError(f"Seed {seed} does not match the text arm's first turn")
            (snapshots / f"{seed:02d}_before.png").write_bytes(before)
            (snapshots / f"{seed:02d}_after.png").write_bytes(after)

            difference = None
            recovery = None
            if not initial["task_completed"] and not initial["truncated"]:
                if options.target_motion:
                    difference = measure_target_motion(
                        before,
                        after,
                        project_cube_center(before_frame, initial_pose),
                        project_cube_center(after_frame, initial["physical_cube_pose_after"]),
                    )
                elif vlm_args:
                    difference = describe_change(vlm_args, before, after, task)
                if not options.single_turn:
                    text = difference["text"] if difference else None
                    messages = recovery_prompt(initial, env._task_prompt, text, task)
                    if options.oracle:
                        program = env.oracle_code
                        generation = {
                            "messages": messages,
                            "raw_response": program,
                            "program": program,
                            "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
                            "request_seconds": 0.0,
                        }
                    else:
                        generation = generate(args, messages)
                    recovery = execute(env, backend, generation)
                    cube_delta_z_cm = 100 * (
                        recovery["physical_cube_pose_after"][2] - initial_pose[2]
                    )
                    recovery["physical_cube_delta_z_cm"] = cube_delta_z_cm
                    if task == "cube_lift":
                        recovery["physical_lift_cm"] = cube_delta_z_cm

            if options.record_overview:
                final_overview = encode_rgb_unpatched(low_level.get_image("overview"))
                (snapshots / f"{seed:02d}_overview.png").write_bytes(final_overview)

            row = {
                "seed": seed,
                "first_state_sha256": first_key,
                "frame_sha256": [before_sha, after_sha],
                "initial": initial,
                "recovery": recovery,
                "vdm": difference,
            }
            report["seed_results"].append(row)
            write_report(report, options.output)
            print(
                f"Seed {seed}: first={initial['task_completed']}, "
                f"failure={initial['failure_reason']}, "
                f"recovery={None if recovery is None else recovery['task_completed']}",
                flush=True,
            )
    finally:
        try:
            env.close()
        finally:
            _stop_api_servers(server_procs)

    rows = report["seed_results"]
    failed = [row for row in rows if not row["initial"]["task_completed"]]
    recovered = sum(bool(row["recovery"] and row["recovery"]["task_completed"]) for row in failed)
    report["summary"] = {
        "trials": len(rows),
        "first_turn_successes": len(rows) - len(failed),
        "recoveries": recovered,
        "first_turn_failures": len(failed),
        "final_successes": len(rows) - len(failed) + recovered,
    }
    if options.target_motion:
        estimates = [row["vdm"] for row in rows if row["vdm"] is not None]
        report["summary"].update(
            visual_estimates=len(estimates),
            correct_visual_directions=sum(item.get("direction_match", False) for item in estimates),
        )
    report["summary"].update(
        oracle=options.oracle,
        perturbation=report["perturbation"],
    )
    write_report(report, options.output)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
