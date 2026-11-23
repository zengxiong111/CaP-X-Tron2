"""Replay a TRON2 tabletop program in the native MuJoCo viewer."""

import argparse
import copy
from importlib.resources import files
from pathlib import Path
from threading import Event
from time import monotonic, sleep

import mujoco
import mujoco.viewer
import numpy as np

from capx.envs.configs.instantiate import instantiate
from capx.envs.configs.loader import DictLoader
from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.envs.tasks.base import CodeExecEnvConfig
from capx.envs.tasks.tron2.cube_lift import Tron2CubeLiftCodeEnv
from capx.integrations.tron2.mujoco_backend import MujocoBackend

PLAYBACK_SPEED = 0.8


def _sync_display_state(backend, display_model, display_data, state):
    state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
    mujoco.mj_getState(backend._model, backend._data, state, state_spec)
    mujoco.mj_setState(display_model, display_data, state, state_spec)
    mujoco.mj_forward(display_model, display_data)


def replay_trial(env, backend, viewer, program, display_model, display_data, state, *, seed, source):
    env.reset(seed=seed)
    initial_z = backend.task_state().cube_pose[2]
    title = "TRON2 Cube Lift" if env.low_level_env.task == "cube_lift" else "TRON2 Pick & Place"
    viewer.set_texts((None, None, title, f"{source} | Seed {seed}\nPlaying..."))
    _sync_display_state(backend, display_model, display_data, state)
    viewer.sync(state_only=True)
    sleep(1.0)

    data = backend._data
    original_step = backend._step_physics
    start_sim = data.time
    start_wall = monotonic()
    next_frame = start_sim

    def step_and_render():
        nonlocal next_frame
        original_step()
        if not viewer.is_running() or data.time < next_frame:
            return
        next_frame = data.time + 1 / 45
        delay = (data.time - start_sim) / PLAYBACK_SPEED - (monotonic() - start_wall)
        if delay > 0:
            sleep(delay)
        _sync_display_state(backend, display_model, display_data, state)
        viewer.sync(state_only=True)

    backend._step_physics = step_and_render
    try:
        _, reward, _, _, result = env.step(program)
    finally:
        backend._step_physics = original_step

    rise_cm = 100 * (backend.task_state().cube_pose[2] - initial_z)
    completed = result["task_completed"]
    status = "PASS" if completed else "FAIL"
    _sync_display_state(backend, display_model, display_data, state)
    viewer.set_texts((
        None, None, title, f"{status} | Cube height change {rise_cm:.2f} cm\nPress R to replay"
    ))
    viewer.sync(state_only=True)
    print(
        f"Seed {seed}: task_completed={completed}, reward={reward}, rise_cm={rise_cm:.4f}",
        flush=True,
    )
    if result["stderr"]:
        print(result["stderr"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="TRON2 MuJoCo task YAML")
    parser.add_argument("--seed", type=int, default=1)
    programs = parser.add_mutually_exclusive_group()
    programs.add_argument("--oracle", action="store_true", help="Replay the task's Oracle")
    programs.add_argument("--program", type=Path, help="Replay a saved Python program")
    options = parser.parse_args()
    if options.config and not (options.oracle or options.program):
        parser.error("--config requires --oracle or --program")
    if options.config:
        env_factory = DictLoader.load(str(options.config))["env"]
        low_level = env_factory["cfg"]["low_level"]
        if low_level["backend"] != "mujoco":
            parser.error("The native viewer requires a MuJoCo config")
        low_level["max_attempts"] = 1
        env = instantiate(env_factory)
        backend = env.low_level_env._backend
    else:
        backend = MujocoBackend()
        env = Tron2CubeLiftCodeEnv(CodeExecEnvConfig(
            low_level=Tron2MujocoEnv(backend=backend, privileged=True, max_attempts=1),
            apis=["Tron2ControlApi"],
        ))
    replay = Event()
    replay.set()

    def on_key(key):
        if key == ord("R"):
            replay.set()

    try:
        if options.oracle:
            program, source = env.oracle_code, "Oracle"
        elif options.program:
            program, source = options.program.read_text(encoding="utf-8"), options.program.name
        else:
            program = files("capx.envs").joinpath(
                "assets", "tron2_tasks", "cube_lift_qwen.txt"
            ).read_text(encoding="utf-8")
            source = "Qwen model"
        env.reset(seed=options.seed)
        model = copy.copy(backend._model)
        display_data = mujoco.MjData(model)
        state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(backend._model, state_spec))
        _sync_display_state(backend, model, display_data, state)
        with mujoco.viewer.launch_passive(
            model, display_data, key_callback=on_key, show_left_ui=False, show_right_ui=False
        ) as viewer:
            with viewer.lock():
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = model.camera("overview").id
                viewer.opt.geomgroup[3] = 0
            while viewer.is_running():
                if replay.wait(timeout=0.05):
                    replay.clear()
                    replay_trial(
                        env, backend, viewer, program, model, display_data, state,
                        seed=options.seed, source=source,
                    )
                else:
                    viewer.sync(state_only=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
