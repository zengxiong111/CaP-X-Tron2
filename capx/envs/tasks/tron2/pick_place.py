"""Move the tabletop cube to the marked region and release it."""

from .base import GRASP_AND_LIFT, TOOL_GUIDANCE, Tron2CodeEnv


class Tron2PickPlaceCodeEnv(Tron2CodeEnv):
    """Pick & Place using the configured source of object poses."""

    task = "pick_place"
    prompt = (
        "Pick up the cube, take it above the marked target region, then set it down "
        'and release it. Read get_object_pose("target") for the desired resting center. '
        "The task is complete when the released cube settles in the region.\n\n" + TOOL_GUIDANCE
    )
    oracle_code = (
        'target = get_object_pose("target")\n'
        + GRASP_AND_LIFT
        + """\

# Use the measured grasp offset to center the cube over the target.
tcp = get_robot_state()["tcp_poses"][arm]
dx, dy, dz = (tcp[i] - lifted_cube[i] for i in range(3))
goal_x, goal_y = target[0] + dx, target[1] + dy
release_z = target[2] + dz + 0.01
transfer_z = max(tcp[2], release_z + 0.09)
move_tcp(goal_x, goal_y, transfer_z, "transfer above target")
move_tcp(goal_x, goal_y, release_z, "lower cube to target")
require_success(open_gripper(arm), "release cube")
move_tcp(goal_x, goal_y, transfer_z, "retreat from target")
"""
    )
