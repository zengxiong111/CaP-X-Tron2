"""Contract tests for the shared TRON2 evaluator's task and perturbation profiles."""

import pytest

from capx.envs.evaluate_tron2_recovery import offset_profile, task_from_config


@pytest.mark.parametrize("task", ["cube_lift", "pick_place"])
def test_task_is_selected_from_low_level_config(task):
    assert task_from_config({"low_level": {"task": task}}) == task


def test_task_defaults_to_cube_lift_for_legacy_config():
    assert task_from_config({"low_level": {}}) == "cube_lift"


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError, match="Unsupported TRON2 task"):
        task_from_config({"low_level": {"task": "stack"}})


@pytest.mark.parametrize(
    ("legacy", "profile", "expected"),
    [
        ("+X", None, "+X"),
        ("+X,-Y", None, "+X,-Y"),
        ("+X,-Y", "cube_shift:+X", "+X"),
        ("+X", "cube_shift:alternating", "+X,-Y"),
        ("+X", "none", "none"),
    ],
)
def test_perturbation_profile_preserves_legacy_and_explicit_modes(legacy, profile, expected):
    assert offset_profile(legacy, profile) == expected
