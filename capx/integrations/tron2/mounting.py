"""Fixed tabletop datum and tested MuJoCo right-arm ready branch."""

import math

import numpy as np

TABLETOP_Z = 0.620
MOUNT_GAP = 0.450
VENDOR_BASE_Z = 1.210
BASE_WORLD_Z = TABLETOP_Z + MOUNT_GAP
RIGHT_GRASP_YAW_OFFSET_DEG = 15.0
RIGHT_GRASP_YAW_RAD = math.pi / 2 + math.radians(RIGHT_GRASP_YAW_OFFSET_DEG)
RIGHT_GRASP_QUATERNION = (
    math.cos(RIGHT_GRASP_YAW_RAD / 2),
    0.0,
    0.0,
    math.sin(RIGHT_GRASP_YAW_RAD / 2),
)

# Joint order matches MujocoBackend._JOINTS; right ready TCP is near the cube
# approach region and was verified on the fixed-gap scene.
RIGHT_READY = np.array((
    1.50289852223072,
    -2.4200518054276943,
    -0.9494541628289997,
    -1.4767557271848775,
    -0.5400267590736921,
    0.6963559623185722,
    0.883901176474163,
))
