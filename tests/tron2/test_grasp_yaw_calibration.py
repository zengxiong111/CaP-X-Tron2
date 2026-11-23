"""The right grasp orientation uses the fixed tabletop margin calibration."""

import math

import numpy as np
import pytest

from capx.integrations.tron2.mounting import (
    RIGHT_GRASP_QUATERNION,
    RIGHT_GRASP_YAW_OFFSET_DEG,
    RIGHT_GRASP_YAW_RAD,
)
from capx.integrations.tron2.mujoco_backend import _TOP_DOWN


def test_right_grasp_quaternion_applies_calibrated_fifteen_degree_yaw():
    assert RIGHT_GRASP_YAW_OFFSET_DEG == 15.0
    assert RIGHT_GRASP_YAW_RAD == pytest.approx(math.radians(105.0), abs=1e-12)
    assert np.allclose(_TOP_DOWN["right"], RIGHT_GRASP_QUATERNION, atol=1e-12, rtol=0)
    assert np.allclose(
        _TOP_DOWN["left"],
        (math.sqrt(.5), 0.0, 0.0, -math.sqrt(.5)),
        atol=1e-12,
        rtol=0,
    )
