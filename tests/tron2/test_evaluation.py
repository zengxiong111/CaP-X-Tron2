"""Exercise TRON2 through CaP-X's YAML loader, executor and trial runner."""

import json
import os
from pathlib import Path

import pytest

from capx.envs import trial
from capx.envs.configs.instantiate import instantiate
from capx.envs.launch import LaunchArgs
from capx.envs.simulators.tron2_mujoco import Tron2MujocoEnv
from capx.integrations.tron2.backends import ObservationUnavailableError
from capx.utils.launch_utils import _load_config

CONFIG_DIR = Path(__file__).resolve().parents[2] / "env_configs" / "tron2"


def build_trial(name, output_dir, *, oracle):
    args = LaunchArgs(
        config_path=str(CONFIG_DIR / f"{name}.yaml"),
        output_dir=str(output_dir),
        use_oracle_code=oracle,
    )
    env_factory, config, _ = _load_config(args)
    return instantiate(env_factory), args, config, env_factory["cfg"]["multi_turn_prompt"]


@pytest.mark.parametrize("task", ["cube_lift", "pick_place"])
def test_mock_oracle_uses_no_model_and_solves_task(task, tmp_path, monkeypatch):
    def no_model(*args, **kwargs):
        pytest.fail("an Oracle trial requested a model response")

    monkeypatch.setattr(trial, "_query_model", no_model)
    env, args, config, prompt = build_trial(f"{task}_mock", tmp_path, oracle=True)
    try:
        initial, _ = env.reset(seed=3)
        repeated, _ = env.reset(seed=3)
        other, _ = env.reset(seed=4)
        assert initial["object_poses"] == repeated["object_poses"]
        assert initial["object_poses"]["cube"] != other["object_poses"]["cube"]
        summary = trial._run_single_trial(env, 3, args, config, prompt)
        assert (summary.task_completed, summary.reward, summary.sandbox_rc) == (True, 1.0, 0)
        assert summary.num_code_blocks == 1
    finally:
        env.close()


def test_failed_grasp_is_observed_and_retried(tmp_path, monkeypatch):
    env, args, config, prompt = build_trial("cube_lift_mock", tmp_path, oracle=False)
    requests = []

    def scripted_model(_args, messages):
        requests.append(messages)
        if len(requests) == 1:
            return {"content": 'close_gripper("right")', "reasoning": None}
        assert len(requests) == 2
        payload = json.dumps(messages)
        assert "TRON2 feedback" in payload and "empty_grasp" in payload and "object_poses" in payload
        return {"content": f"REGENERATE\n```python\n{env.oracle_code}\n```", "reasoning": None}

    monkeypatch.setattr(trial, "_query_model", scripted_model)
    try:
        summary = trial._run_single_trial(env, 1, args, config, prompt)
        assert summary.task_completed is True
        assert summary.terminated and not summary.truncated
        assert summary.num_regenerations == 1
        assert summary.num_code_blocks == len(requests) == 2
    finally:
        env.close()


def test_unprivileged_observation_and_command_limits():
    env = Tron2MujocoEnv(backend="mock", privileged=False, max_steps=2)
    try:
        observation, _ = env.reset(seed=1)
        assert "object_poses" not in observation
        with pytest.raises(ObservationUnavailableError):
            env.get_object_pose("cube")
        with pytest.raises(ObservationUnavailableError):
            env.get_image("head")

        start = env.get_robot_state()["tcp_poses"]["right"]
        invalid = env.move_ee("right", (*start[:3], 0, 0, 0, 0))
        assert not invalid.success and invalid.code == "invalid_command"
        slow = env.move_ee("right", (start[0] + 0.05, *start[1:]), speed=1e-300)
        assert not slow.success and slow.code == "timeout"
        assert env.get_robot_state()["tcp_poses"]["right"] == start
        assert env.episode_info()["episode_truncated"] is True
        assert not env.open_gripper("right").success
    finally:
        env.close()


@pytest.mark.skipif(not os.getenv("TRON2_MJCF_PATH"), reason="requires the official DACH_TRON2A model")
@pytest.mark.parametrize("task", ["cube_lift", "pick_place"])
def test_mujoco_s1_oracle(task, tmp_path):
    pytest.importorskip("mujoco")
    env, args, config, prompt = build_trial(f"{task}_s1", tmp_path, oracle=True)
    try:
        summary = trial._run_single_trial(env, 1, args, config, prompt)
        assert (summary.task_completed, summary.reward, summary.sandbox_rc) == (True, 1.0, 0)
    finally:
        env.close()


@pytest.mark.skipif(
    not (os.getenv("TRON2_MJCF_PATH") and os.getenv("TRON2_TEST_RENDER") == "1"),
    reason="requires the DACH_TRON2A model and a MuJoCo rendering context",
)
def test_mujoco_s2_estimates_pose_and_solves_task(tmp_path):
    pytest.importorskip("mujoco")
    from math import dist

    env, args, config, prompt = build_trial("pick_place_s2", tmp_path, oracle=True)
    privileged = Tron2MujocoEnv(privileged=True)
    try:
        visuals, _ = env.reset(seed=1)
        truth, _ = privileged.reset(seed=1)
        assert "object_poses" not in visuals
        assert "robot0_robotview" in visuals
        for name in ("cube", "target"):
            estimated = env.low_level_env.get_object_pose(name)
            assert dist(estimated[:3], truth["object_poses"][name][:3]) < 0.005
        summary = trial._run_single_trial(env, 1, args, config, prompt)
        assert (summary.task_completed, summary.reward, summary.sandbox_rc) == (True, 1.0, 0)
    finally:
        env.close()
        privileged.close()
