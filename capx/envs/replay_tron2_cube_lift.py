"""Play the saved Cube Lift program in the native MuJoCo viewer."""

from importlib.resources import files
from threading import Event
from time import monotonic, sleep

import mujoco
import mujoco.viewer

from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.envs.tasks.base import CodeExecEnvConfig
from capx.envs.tasks.tron2.cube_lift import Tron2CubeLiftCodeEnv
from capx.integrations.tron2.mujoco_backend import MujocoBackend

SEED = 1
PLAYBACK_SPEED = 0.8


def replay_trial(env, backend, viewer, program):
    observation, _ = env.reset(seed=SEED)
    initial_z = observation["object_poses"]["cube"][2]
    viewer.set_texts((None, None, "TRON2 Cube Lift", "Qwen model | Seed 1\nPlaying..."))
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
        viewer.sync(state_only=True)

    backend._step_physics = step_and_render
    try:
        observation, reward, _, _, result = env.step(program)
    finally:
        backend._step_physics = original_step

    rise_cm = 100 * (observation["object_poses"]["cube"][2] - initial_z)
    completed = result["task_completed"]
    status = "PASS" if completed else "FAIL"
    viewer.set_texts((
        None, None, "TRON2 Cube Lift", f"{status} | Rise {rise_cm:.2f} cm\nPress R to replay"
    ))
    viewer.sync(state_only=True)
    print(f"Seed {SEED}: task_completed={completed}, reward={reward}, rise_cm={rise_cm:.4f}", flush=True)
    if result["stderr"]:
        print(result["stderr"], flush=True)


def main():
    program = files("capx.envs").joinpath(
        "assets", "tron2_tasks", "cube_lift_qwen.txt"
    ).read_text(encoding="utf-8")
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
        env.reset(seed=SEED)
        model = backend._model
        with mujoco.viewer.launch_passive(
            model, backend._data, key_callback=on_key, show_left_ui=False, show_right_ui=False
        ) as viewer:
            with viewer.lock():
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = model.camera("overview").id
                viewer.opt.geomgroup[3] = 0
            while viewer.is_running():
                if replay.wait(timeout=0.05):
                    replay.clear()
                    replay_trial(env, backend, viewer, program)
                else:
                    viewer.sync(state_only=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
