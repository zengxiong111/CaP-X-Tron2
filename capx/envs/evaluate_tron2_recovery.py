"""Compare two-turn Cube Lift recovery with RGB-D and optional visual differencing."""

import argparse
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import signal
from time import monotonic

from PIL import Image

from capx.envs.configs.loader import DictLoader
from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.envs.tasks.base import CodeExecEnvConfig
from capx.envs.tasks.tron2.cube_lift import Tron2CubeLiftCodeEnv
from capx.envs.trial import _get_visual_differencing_feedback
from capx.integrations.tron2.recovery_backend import RecoveryMujocoBackend
from capx.llm.client import ModelQueryArgs, query_model
from capx.utils.launch_utils import _extract_code


def generate(args, messages):
    started = monotonic()
    response = query_model(args, messages)
    program, = _extract_code(response["content"])
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
    step_offset = env.low_level_env.episode_info()["steps"]
    old_handler = signal.signal(signal.SIGALRM, interrupt_script)
    signal.setitimer(signal.ITIMER_REAL, 15)
    try:
        observation, reward, terminated, truncated, info = env.step(generation["program"])
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    assert "object_poses" not in observation, "unexpected privileged observation"
    robot = observation["robot_state"]
    return {
        "task_completed": info["task_completed"],
        "reward": reward,
        "terminated": terminated,
        "truncated": truncated,
        "sandbox_rc": info["sandbox_rc"],
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


def capture_rgb(env, camera):
    frame = env.get_image(camera)
    with BytesIO() as stream:
        Image.fromarray(frame["rgb"]).save(stream, format="PNG")
        return stream.getvalue()


def recovery_prompt(first, task_prompt, visual_diff=None):
    feedback = {
        "failure_reason": first["failure_reason"],
        "failed_actions": [action for action in first["actions"] if not action["success"]],
        "grasped_by": first["grasped_by_after"],
        "right_tcp": first["right_tcp"],
    }
    content = (
        "The first program just ran. Continue from its resulting state in the same "
        "episode. Simulator feedback: " + json.dumps(feedback) + "\n"
        "Start the recovery program by reading the new cube pose using get_object_pose. "
        "Use the current cube coordinates for every action, because the original grasp "
        "coordinates are stale. The right gripper is not holding the cube in an empty "
        "grasp. Open it, approach above the current cube, descend, close, and lift. "
        "The procedure below refers to the pose at the start of this recovery program.\n"
        + task_prompt
    )
    if visual_diff is not None:
        content += "\nVisual difference from two RGB snapshots: " + visual_diff
    return [
        {"role": "system", "content": "You generate executable Python for a robot simulator."},
        {"role": "user", "content": content},
    ]


def describe_change(args, before, after):
    images = ["data:image/png;base64," + base64.b64encode(frame).decode() for frame in (before, after)]
    start = monotonic()
    description = _get_visual_differencing_feedback(
        args, "Lift the red cube and hold it in the right gripper.", images
    )
    elapsed = monotonic() - start
    if not description or not description.strip():
        raise RuntimeError("The VLM returned an empty visual difference")
    return {"text": description.strip(), "request_seconds": elapsed}


def write_report(report, output):
    temporary = output.with_name(output.name + ".partial")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--camera", choices=("head", "overview"), default="head")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--vdm-model")
    parser.add_argument("--vdm-server-url")
    options = parser.parse_args()
    if options.trials < 1 or options.output.exists():
        parser.error("Use a positive trial count and a new output path")
    vdm_settings = (options.baseline, options.vdm_model, options.vdm_server_url)
    if any(vdm_settings) and not all(vdm_settings):
        parser.error("The VDM arm requires --baseline, --vdm-model and --vdm-server-url")

    config = DictLoader.load(str(options.config))["env"]["cfg"]
    args = ModelQueryArgs(
        model=options.model,
        server_url=options.server_url,
        temperature=0,
        max_tokens=768,
    )
    baseline_rows = {}
    first_generation = None
    vlm_args = None
    if options.baseline is not None:
        baseline = json.loads(options.baseline.read_text(encoding="utf-8"))
        if (
            baseline["variant"] != "text" or baseline["camera"] != options.camera
            or baseline["model"] != options.model
        ):
            parser.error("The baseline must use the same camera and code model, with text feedback")
        baseline_rows = {row["seed"]: row for row in baseline["seed_results"]}
        if set(range(1, options.trials + 1)) - set(baseline_rows):
            parser.error("The baseline must contain every requested trial seed")
        first_generation = baseline_rows[1]["initial"]["generation"]
        vlm_args = ModelQueryArgs(
            model=options.vdm_model, server_url=options.vdm_server_url,
            temperature=0, max_tokens=96,
        )

    snapshots = options.output.parent / (options.output.stem + "_frames")
    snapshots.mkdir(parents=True)
    backend = RecoveryMujocoBackend()
    low_level = Tron2MujocoEnv(
        backend=backend, task="cube_lift", privileged=False,
        enable_render=True, visual_pose=True, max_attempts=2,
    )
    env = Tron2CubeLiftCodeEnv(CodeExecEnvConfig(
        low_level=low_level, apis=config["apis"], prompt=config["prompt"],
    ))
    report = {
        "format_version": 1,
        "variant": "vdm" if vlm_args else "text",
        "model": args.model,
        "camera": options.camera,
        "vlm_model": options.vdm_model,
        "seed_results": [],
    }
    try:
        for seed in range(1, options.trials + 1):
            obs, _ = env.reset(seed=seed, options={"trial": seed})
            assert "object_poses" not in obs, "unexpected privileged initial observation"
            initial_messages = deepcopy(obs["full_prompt"])
            if first_generation is None:
                first_generation = generate(args, initial_messages)
            if initial_messages != first_generation["messages"]:
                raise RuntimeError("Initial model prompt changed")
            initial_z = backend.task_state().cube_pose[2]
            before = capture_rgb(low_level, options.camera)
            initial = execute(env, backend, first_generation)
            initial["disturbance"] = deepcopy(backend.disturbance)
            first_key = first_state_sha256(backend, initial)
            after = capture_rgb(low_level, options.camera)
            before_sha = hashlib.sha256(before).hexdigest()
            after_sha = hashlib.sha256(after).hexdigest()
            if vlm_args:
                baseline_row = baseline_rows[seed]
                expected = (baseline_row["first_state_sha256"], *baseline_row["frame_sha256"])
                if (first_key, before_sha, after_sha) != expected:
                    raise RuntimeError(f"Seed {seed} does not match the text arm's first turn")
            (snapshots / f"{seed:02d}_before.png").write_bytes(before)
            (snapshots / f"{seed:02d}_after.png").write_bytes(after)

            difference = None
            recovery = None
            if not initial["task_completed"] and not initial["truncated"]:
                if vlm_args:
                    difference = describe_change(vlm_args, before, after)
                text = difference["text"] if difference else None
                generation = generate(args, recovery_prompt(initial, config["prompt"], text))
                recovery = execute(env, backend, generation)
                recovery["physical_lift_cm"] = 100 * (recovery["physical_cube_pose_after"][2] - initial_z)

            row = {
                "seed": seed, "first_state_sha256": first_key,
                "frame_sha256": [before_sha, after_sha],
                "initial": initial, "recovery": recovery, "vdm": difference,
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
        env.close()

    rows = report["seed_results"]
    failed = [row for row in rows if not row["initial"]["task_completed"]]
    recovered = sum(
        bool(row["recovery"] and row["recovery"]["task_completed"]) for row in failed
    )
    report["summary"] = {
        "trials": len(rows),
        "first_turn_successes": len(rows) - len(failed),
        "recoveries": recovered,
        "first_turn_failures": len(failed),
        "final_successes": len(rows) - len(failed) + recovered,
    }
    write_report(report, options.output)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
