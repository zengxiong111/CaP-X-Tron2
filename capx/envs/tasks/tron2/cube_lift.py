"""Lift the tabletop cube and hold it in the gripper."""

from .base import GRASP_AND_LIFT, TOOL_GUIDANCE, Tron2CodeEnv


class Tron2CubeLiftCodeEnv(Tron2CodeEnv):
    """Cube Lift using the configured source of object poses."""

    task = "cube_lift"
    prompt = (
        "Pick up the cube from the table and raise its center at least 0.07 m above "
        "its starting height. Hold it still in the gripper after the lift.\n\n" + TOOL_GUIDANCE
    )
    oracle_code = GRASP_AND_LIFT
