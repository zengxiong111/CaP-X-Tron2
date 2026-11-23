"""Tabletop manipulation with the external LimX DACH_TRON2A MJCF.

The vendor assets stay in their own checkout. The task scene adds a fixed
stand, probe sites, a table, and free cubes without changing any source assets.
"""

from __future__ import annotations

import math
import os
from importlib.resources import files
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from .backends import ActionResult, Arm, CameraFrame, ObservationUnavailableError, Pose, TaskState
from .mounting import (
    BASE_WORLD_Z,
    MOUNT_GAP,
    RIGHT_GRASP_QUATERNION,
    RIGHT_READY,
    TABLETOP_Z,
    VENDOR_BASE_Z,
)
from .safety import validate_arm, validate_move

_ARMS: dict[Arm, str] = {"left": "L", "right": "R"}
_JOINTS = (
    "proximal_pitch",
    "proximal_roll",
    "proximal_yaw",
    "elbow",
    "wrist_yaw",
    "wrist_pitch",
    "wrist_roll",
)
_SPAWN_MIN = (.343, -.214)
_SPAWN_MAX = (.385, -.178)
_IDENTITY = (1.0, 0.0, 0.0, 0.0)
_TOP_DOWN = {
    "left": (math.sqrt(.5), 0.0, 0.0, -math.sqrt(.5)),
    "right": RIGHT_GRASP_QUATERNION,
}
_TCP_OFFSET = (0.0, 0.0, -0.168)
_WIDTH, _HEIGHT = 480, 360
_MAX_MOTION_SECONDS = 8.0
_MAX_JOINT_SPEED = 0.85
_MOTION_SETTLE_SECONDS = 0.14
_MOUNTED_BASE_Z = BASE_WORLD_Z


def _xml_vector(values: tuple[float, ...]) -> str:
    return " ".join(map(str, values))


def _scene(path: Path) -> str:
    root = ET.parse(path).getroot()
    compiler = root.find("compiler")
    world = root.find("worldbody")
    base = root.find(".//body[@name='base_Link']")
    option = root.find("option")
    contacts = root.find("contact")
    if compiler is None or world is None or base is None or option is None or contacts is None:
        raise ValueError("Expected the LimX DACH_TRON2A robot_grasper.xml model.")
    compiler.set("meshdir", str((path.parent / compiler.get("meshdir", ".")).resolve()))
    base_xyz = [float(value) for value in base.get("pos", "").split()]
    if len(base_xyz) != 3 or not (np.isclose(base_xyz[2], VENDOR_BASE_Z, atol=1e-9, rtol=0)
                                  or np.isclose(base_xyz[2], _MOUNTED_BASE_Z, atol=1e-9, rtol=0)):
        raise ValueError("The vendor base must be at Z=1.210 m or the calibrated Z=1.070 m.")
    base_xyz[2] = _MOUNTED_BASE_Z  # Normalize exactly once, including calibrated overlays.
    base.set("pos", _xml_vector(tuple(base_xyz)))
    # The vendor stand mesh extends ~0.13035 m below this datum. Preserve all
    # link transforms and represent the simulated recess in collision and RGB.
    ground = world.find("geom[@name='ground']")
    if ground is None:
        raise ValueError("The vendor model must include its ground geom.")
    world.remove(ground)
    # Keep tiles finite (4 x 4 m) so MuJoCo's inferred camera clipping planes
    # remain appropriate for the tabletop scene.
    _mount_box(world, "ground", (-1.19, 0, -.02), (.81, 2, .02), ".2 .3 .4 1")
    _mount_box(world, "mount_floor_east", (1.19, 0, -.02), (.81, 2, .02), ".2 .3 .4 1")
    _mount_box(world, "mount_floor_north", (0, 1.19, -.02), (.38, .81, .02), ".2 .3 .4 1")
    _mount_box(world, "mount_floor_south", (0, -1.19, -.02), (.38, .81, .02), ".2 .3 .4 1")
    # 760 x 760 mm aperture around the vendor foot and a rendered, collidable
    # support plate. Its top is 1 mm above the measured stand minimum (-.13035).
    _mount_box(world, "mount_recess_floor", (0, 0, -.13435), (.365, .365, .005), ".3 .32 .34 1")
    for name, pos, size in (
        ("left_wall", (-.38, 0, -.070175), (.01, .38, .070175)),
        ("right_wall", (.38, 0, -.070175), (.01, .38, .070175)),
        ("front_wall", (0, -.38, -.070175), (.38, .01, .070175)),
        ("back_wall", (0, .38, -.070175), (.38, .01, .070175)),
    ):
        _mount_box(world, "mount_recess_" + name, pos, size, ".32 .34 .36 1")
    free_base = base.find("joint[@type='free']")
    if free_base is not None:
        base.remove(free_base)
    for geom in base.iter("geom"):
        if geom.get("class") != "visual":
            geom.set("group", "3")  # Diagnostic collision surfaces are hidden from RGB-D.
    for side in _ARMS:
        for geom in world.findall(f"./body[@name='target_{side}_body']/geom"):
            geom.set("group", "3")  # Hide the vendor's mocap axes as well.
    for suffix in _ARMS.values():
        # Removing the free joint makes the stand static. Preserve parent-child
        # filtering at the shoulder hinge, where the vendor meshes overlap.
        ET.SubElement(contacts, "exclude", body1="base_Link", body2=f"proximal_pitch_{suffix}_Link")

    option.set("integrator", "implicitfast")
    # The stock linkage has a 1 ms time step and four-bar joints.
    # A soft no-slip solve leaves the fingers' friction as the sole hold mechanism.
    option.set("iterations", "40")
    option.set("noslip_iterations", "8")

    for side, suffix in _ARMS.items():
        gripper = root.find(f".//body[@name='grasper_base_{suffix}_Link']")
        if gripper is None:
            raise ValueError("The DACH model must include both 2F grippers.")
        swivel = gripper.find(f"joint[@name='grasper_base_{suffix}_Joint']")
        if swivel is None:
            raise ValueError("The DACH gripper swivel joint is missing.")
        # Model the drivetrain inertia on the held swivel joint so the position
        # servo remains damped at the vendor physics timestep.
        swivel.set("armature", ".012")
        ET.SubElement(
            gripper, "site", name=f"task_tcp_{side}", pos=_xml_vector(_TCP_OFFSET),
            size=".004", rgba="0.1 0.8 0.2 0",
        )
        ET.SubElement(
            gripper, "camera", name=f"{side}_wrist", pos="-.048 0 -.056",
            xyaxes="1 0 0 0 1 0", fovy="72",
        )
        for jaw, sign in (("left", -1), ("right", 1)):
            name = f"grasper_{suffix}_jaw_{jaw}_Link"
            body = root.find(f".//body[@name='{name}']")
            geom = body.find("geom[@class='collision']") if body is not None else None
            if body is None or geom is None:
                raise ValueError(f"The DACH model is missing the collision mesh for {name}.")
            # Keep the vendor outline for robot and table collisions. A flat
            # contact pad at the STL's inner finger tip gives the cube a
            # defined gripping surface instead of the convex hull's bevel.
            geom.set("contype", "4")
            geom.set("conaffinity", "5")
            ET.SubElement(
                body, "geom", name=name, type="box", size=".0135 .004 .011",
                pos=_xml_vector((0, sign * .0075, -.051)), density="0", group="3",
                condim="4", friction="1.5 .015 .001", margin=".0002",
                solref=".009 1", rgba=".25 .25 .25 0",
            )
    head = root.find(".//body[@name='head_pitch_Link']")
    if head is None:
        raise ValueError("The DACH model must include a head pitch link.")
    ET.SubElement(head, "camera", name="head", pos=".082 -.03 -.01", fovy="55",
                  xyaxes="0 -1 0 .943 0 .333")

    scene = files("capx.envs").joinpath("assets", "tron2_tasks", "tabletop.xml")
    with scene.open("rb") as asset:
        tabletop = ET.parse(asset).getroot().find("worldbody")
    if tabletop is None:
        raise ValueError("The TRON2 tabletop asset must define a worldbody.")
    world.extend(tabletop)

    return ET.tostring(root, encoding="unicode")


def _mount_box(world: ET.Element, name: str, pos: tuple[float, float, float],
               half_size: tuple[float, float, float], rgba: str) -> None:
    ET.SubElement(world, "geom", name=name, type="box", pos=_xml_vector(pos),
                  size=_xml_vector(half_size), rgba=rgba, contype="1", conaffinity="1",
                  condim="3", friction="1 .3 .3", margin=".001")


class MujocoBackend:
    """In-process physics backend that never connects to a robot controller."""

    def __init__(
        self, model_path: str | os.PathLike[str] | None = None, *, enable_render: bool = False
    ) -> None:
        model_path = model_path or os.environ.get("TRON2_MJCF_PATH")
        if not model_path:
            raise ValueError(
                "Set TRON2_MJCF_PATH to the external DACH_TRON2A xml/robot_grasper.xml "
                "(with its sibling meshes directory). See docs/tron2_bringup.md."
            )
        path = Path(model_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"DACH_TRON2A MJCF not found: {path}")
        try:
            import mujoco
        except ImportError as error:
            raise ImportError("Install 'mujoco>=3.2.2,<4' for the TRON2 simulation.") from error

        self._mj = mujoco
        self._model = model = mujoco.MjModel.from_xml_string(_scene(path))
        self._data = mujoco.MjData(model)
        self._planner_data = mujoco.MjData(model)
        self._enable_render = enable_render
        self._renderer = None
        self._closed = False
        self._base_pos = model.body("base_Link").pos.copy()
        table = model.geom("task_table")
        if not np.allclose(model.body("base_Link").quat, _IDENTITY) or model.body(
            "base_Link"
        ).parentid[0] != 0:
            raise ValueError("The external DACH base must be fixed and aligned with the world.")
        tabletop_z = table.pos[2] + table.size[2]
        if not np.allclose((tabletop_z, self._base_pos[2] - tabletop_z),
                           (TABLETOP_Z, MOUNT_GAP), atol=1e-9, rtol=0):
            raise ValueError("The MuJoCo scene must use tabletop Z=0.620 m and mount gap=0.450 m.")
        self._cube_joint = int(model.joint("task_cube").qposadr[0])
        self._cube_dof = int(model.joint("task_cube").dofadr[0])
        cube = model.geom("task_cube")
        self._cube_geom = cube.id
        goal = model.site("task_goal").pos.copy()
        goal[2] = table.pos[2] + table.size[2] + cube.size[2]
        self._goal_position = goal - self._base_pos
        self._actor_geoms = {
            geom.id for i in range(model.ngeom) if model.geom_contype[i] != 0
            and (geom := model.geom(i)).name not in {
                "ground", "mount_floor_east", "mount_floor_north", "mount_floor_south",
                "mount_recess_floor", "mount_recess_left_wall", "mount_recess_right_wall",
                "mount_recess_front_wall", "mount_recess_back_wall",
                "task_table", "task_cube", "task_distractor"
            }
        }
        self._base_geoms = {
            geom for geom in self._actor_geoms
            if model.geom_bodyid[geom] in {model.body("base_3_Link").id, model.body("base_2_Link").id}
        }
        self._ground_geoms = {model.geom(name).id for name in (
            "ground", "mount_floor_east", "mount_floor_north", "mount_floor_south",
            "mount_recess_floor", "mount_recess_left_wall", "mount_recess_right_wall",
            "mount_recess_front_wall", "mount_recess_back_wall",
        )}
        self._jaws = {
            arm: frozenset(model.geom(f"grasper_{suffix}_jaw_{jaw}_Link").id
                           for jaw in ("left", "right"))
            for arm, suffix in _ARMS.items()
        }
        self._sites = {arm: model.site(f"task_tcp_{arm}").id for arm in _ARMS}
        self._arm_actuators = {
            arm: [model.actuator(f"{prefix}_{suffix}").id for prefix in _JOINTS]
            for arm, suffix in _ARMS.items()
        }
        self._drive_actuators = {
            arm: model.actuator(f"grasper_{suffix}_drive_Joint_ctrl").id
            for arm, suffix in _ARMS.items()
        }
        joint_ids = model.actuator_trnid[:, 0]
        self._joint_names = [model.joint(int(joint_id)).name for joint_id in joint_ids]
        self._joint_qpos = model.jnt_qposadr[joint_ids]
        self._joint_dof = model.jnt_dofadr[joint_ids]
        self._limits = model.jnt_range[joint_ids].copy()
        self._kp = np.full(model.nu, 75.0)
        self._kd = np.full(model.nu, 3.0)
        for suffix in _ARMS.values():
            twist = model.actuator(f"grasper_base_{suffix}_Joint_ctrl").id
            self._kp[twist] = 180
            self._kd[twist] = 2.2
        for actuators in self._arm_actuators.values():
            self._kp[actuators] = (850, 850, 580, 650, 220, 250, 180)
            self._kd[actuators] = (43, 43, 23, 26, 9, 11, 7)
        self._targets = np.zeros(model.nu)
        self._gripper_goal = {arm: self._limits[act, 1] for arm, act in self._drive_actuators.items()}

    def reset(self, seed: int | None = None) -> None:
        self._ensure_open()
        mj, model, data = self._mj, self._model, self._data
        rng = np.random.default_rng(seed)
        mj.mj_resetData(model, data)
        data.qpos[self._cube_joint:self._cube_joint + 2] = rng.uniform(_SPAWN_MIN, _SPAWN_MAX)
        self._targets[:] = 0
        for arm, suffix in _ARMS.items():
            drive = self._drive_actuators[arm]
            opening = self._limits[drive, 1]
            # Initialize the driven and following joints on the same part of their 4-bar travel.
            for name in ("drive", "crank_right", "bar_left", "bar_right", "tip_left", "tip_right", "nut"):
                joint = model.joint(f"grasper_{suffix}_{name}_Joint")
                qpos = {
                    "tip_left": -opening,
                    "tip_right": -opening,
                    "nut": .02 * opening,
                }.get(name, opening)
                data.qpos[int(joint.qposadr[0])] = qpos
            self._targets[drive] = self._gripper_goal[arm] = opening
        mj.mj_forward(model, data)
        for arm, side in (("left", 1), ("right", -1)):
            ids = self._arm_actuators[arm]
            if arm == "right":
                q = RIGHT_READY.copy()
                if np.any(self._limits[ids, 0] >= q) or np.any(self._limits[ids, 1] <= q):
                    raise RuntimeError("The fixed-gap right-arm ready pose exceeds joint limits.")
                self._targets[ids] = q
                data.qpos[self._joint_qpos[ids]] = q
                mj.mj_forward(model, data)
                continue
            home = np.array((.31, side * .246, -.444, *_TOP_DOWN[arm]))
            guess = np.array((-.6, side * .1, 0, -.2, 0, .65, 0))
            q = self._inverse_kinematics(arm, home, guess)
            if q is None:
                raise RuntimeError(f"Cannot reach the DACH {arm} arm home pose.")
            self._targets[ids] = q
            data.qpos[self._joint_qpos[ids]] = q
            mj.mj_forward(model, data)
        self.advance(.35)
        collision = self._unexpected_contact(data)
        if collision:
            raise RuntimeError(f"DACH home pose has an unexpected collision: {collision}")

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("The MuJoCo backend is closed.")

    def _site_pose(self, site: int) -> Pose:
        transform = self._data.site_xmat[site]
        quat = np.empty(4)
        self._mj.mju_mat2Quat(quat, transform)
        position = self._data.site_xpos[site] - self._base_pos
        return tuple(map(float, (*position, *quat)))

    def get_robot_state(self) -> dict:
        self._ensure_open()
        positions = self._data.qpos[self._joint_qpos]
        velocities = self._data.qvel[self._joint_dof]
        return {
            "tcp_poses": {arm: self._site_pose(site) for arm, site in self._sites.items()},
            "grippers": {arm: "open" if self._is_open(arm) else "closed" for arm in _ARMS},
            "grasp_quaternions": _TOP_DOWN.copy(),
            "grasped_by": self._grasped_by(),
            "model": "DACH_TRON2A",
            "joint_positions": dict(zip(self._joint_names, map(float, positions), strict=True)),
            "joint_velocities": dict(zip(self._joint_names, map(float, velocities), strict=True)),
            "timestamp": float(self._data.time),
        }

    def get_object_pose(self, name: str) -> Pose:
        self._ensure_open()
        if name == "target":
            return tuple(map(float, (*self._goal_position, *_IDENTITY)))
        if name != "cube":
            raise ObservationUnavailableError(f"Unknown object {name!r}. Use 'cube' or 'target'.")
        qpos = self._data.qpos[self._cube_joint:self._cube_joint + 7].copy()
        qpos[:3] -= self._base_pos
        return tuple(map(float, qpos))

    def get_image(self, camera_name: str) -> CameraFrame:
        self._ensure_open()
        if not self._enable_render:
            raise ObservationUnavailableError("Rendering is disabled for this simulation.")
        try:
            camera = self._model.camera(camera_name)
        except KeyError as error:
            raise ObservationUnavailableError(f"Unknown camera {camera_name!r}.") from error
        try:
            if self._renderer is None:
                self._renderer = self._mj.Renderer(self._model, height=_HEIGHT, width=_WIDTH)
            self._renderer.update_scene(self._data, camera=camera.id)
            rgb = self._renderer.render().copy()
            self._renderer.enable_depth_rendering()
            try:
                depth = self._renderer.render().copy()
            finally:
                self._renderer.disable_depth_rendering()
        except (self._mj.FatalError, RuntimeError, ValueError) as error:
            raise ObservationUnavailableError(f"Cannot render {camera_name!r}: {error}") from error
        focal = _HEIGHT / (2 * math.tan(math.radians(float(camera.fovy[0])) / 2))
        intrinsics = np.array(
            ((focal, 0, (_WIDTH - 1) / 2), (0, focal, (_HEIGHT - 1) / 2), (0, 0, 1))
        )
        pose = np.eye(4)
        pose[:3, :3] = self._data.cam_xmat[camera.id].reshape(3, 3) @ np.diag([1, -1, -1])
        pose[:3, 3] = self._data.cam_xpos[camera.id] - self._base_pos
        return {
            "rgb": rgb, "depth": depth, "K": intrinsics, "T_base_camera": pose,
            "timestamp": float(self._data.time),
        }

    def _is_open(self, arm: Arm) -> bool:
        drive = self._drive_actuators[arm]
        return bool(
            self._data.qpos[self._joint_qpos[drive]] >= self._limits[drive, 1] - .055
        )

    def _grasped_by(self) -> Arm | None:
        cube_touches = set()
        for contact in self._data.contact:
            if contact.efc_address < 0:
                continue
            if contact.geom1 == self._cube_geom:
                cube_touches.add(contact.geom2)
            elif contact.geom2 == self._cube_geom:
                cube_touches.add(contact.geom1)
        for arm, jaws in self._jaws.items():
            if jaws <= cube_touches:
                return arm
        return None

    def task_state(self) -> TaskState:
        self._ensure_open()
        return TaskState(
            cube_pose=self.get_object_pose("cube"),
            cube_speed=float(np.linalg.norm(self._data.qvel[self._cube_dof:self._cube_dof + 3])),
            grasped_by=self._grasped_by(),
            open_grippers=frozenset(arm for arm in _ARMS if self._is_open(arm)),
            timestamp=float(self._data.time),
        )

    def _step_physics(self) -> None:
        model, data = self._model, self._data
        self._mj.mj_step1(model, data)
        position = data.qpos[self._joint_qpos]
        velocity = data.qvel[self._joint_dof]
        torque = self._kp * (self._targets - position) - self._kd * velocity
        torque += data.qfrc_bias[self._joint_dof]
        for arm, act in self._drive_actuators.items():
            # Vendor range and rate. Closing against an object holds at the physically constrained angle.
            delta = self._gripper_goal[arm] - self._targets[act]
            rate = (self._limits[act, 1] - self._limits[act, 0]) * model.opt.timestep
            self._targets[act] += np.clip(delta, -rate, rate)
            effort = 2.0 * (self._targets[act] - position[act]) - 0.05 * velocity[act]
            torque[act] = np.clip(effort, -.25, .60)
        data.ctrl[:] = np.clip(torque, model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1])
        self._mj.mj_step2(model, data)

    def advance(self, seconds: float) -> None:
        self._ensure_open()
        if not math.isfinite(seconds) or not 0 <= seconds <= 5:
            raise ValueError("Simulation advance must be between 0 and 5 seconds.")
        for _ in range(math.ceil(seconds / self._model.opt.timestep)):
            self._step_physics()
        self._mj.mj_forward(self._model, self._data)

    def _unexpected_contact(self, data) -> str | None:
        for contact in data.contact:
            if contact.dist >= -.001:
                continue
            a, b = contact.geom1, contact.geom2
            if a not in self._actor_geoms and b not in self._actor_geoms:
                continue
            if self._cube_geom in (a, b) and any(a in jaws or b in jaws for jaws in self._jaws.values()):
                continue
            if (a in self._ground_geoms or b in self._ground_geoms) and (
                a in self._base_geoms or b in self._base_geoms
            ):
                continue
            return f"{self._model.geom(a).name or self._model.body(self._model.geom_bodyid[a]).name} " \
                   f"and {self._model.geom(b).name or self._model.body(self._model.geom_bodyid[b]).name}"
        return None

    def _inverse_kinematics(self, arm: Arm, pose: np.ndarray, guess: np.ndarray) -> np.ndarray | None:
        mj, model, probe = self._mj, self._model, self._planner_data
        q = guess.copy()
        ids = self._arm_actuators[arm]
        qpos, dofs = self._joint_qpos[ids], self._joint_dof[ids]
        lower, upper = self._limits[ids].T
        site = self._sites[arm]
        jacp = np.empty((3, model.nv))
        jacr = np.empty_like(jacp)
        quat, angle_local = np.empty(4), np.empty(3)
        weight = .22
        probe.qpos[:] = self._data.qpos
        for _ in range(110):
            probe.qpos[qpos] = q
            mj.mj_kinematics(model, probe)
            mj.mj_comPos(model, probe)
            position_err = pose[:3] + self._base_pos - probe.site_xpos[site]
            orientation = probe.site_xmat[site]
            mj.mju_mat2Quat(quat, orientation)
            mj.mju_subQuat(angle_local, pose[3:], quat)
            if np.linalg.norm(position_err) < .00055 and np.linalg.norm(angle_local) < .008:
                return q
            mj.mj_jacSite(model, probe, jacp, jacr, site)
            jac = np.concatenate((jacp[:, dofs], weight * jacr[:, dofs]))
            error = np.concatenate((position_err, weight * orientation.reshape(3, 3) @ angle_local))
            delta = jac.T @ np.linalg.solve(jac @ jac.T + .003 ** 2 * np.eye(6), error)
            q = np.clip(q + np.clip(delta, -.10, .10), lower + .0005, upper - .0005)
        return None

    def move_ee(self, arm: Arm, pose_base: Pose, speed: float) -> ActionResult:
        self._ensure_open()
        try:
            arm, pose_base, speed = validate_move(arm, pose_base, speed)
        except ValueError as error:
            return ActionResult(False, "invalid_command", str(error))

        x, y, z = pose_base[:3]
        if not (.12 <= x <= .63 and -.48 <= y <= .48 and -.578 <= z <= .16):
            return ActionResult(False, "workspace", "Target TCP is outside the tabletop workspace.")
        current = np.asarray(self._site_pose(self._sites[arm]))
        target = np.asarray(pose_base)
        if np.dot(current[3:], target[3:]) < 0:
            target[3:] *= -1
        angle = 2 * math.acos(float(np.clip(np.dot(current[3:], target[3:]), -1, 1)))
        distance = float(np.linalg.norm(target[:3] - current[:3]))
        duration = max(distance / speed, angle / _MAX_JOINT_SPEED, .15)
        if not math.isfinite(duration) or duration > _MAX_MOTION_SECONDS:
            return ActionResult(False, "timeout", "The requested trajectory needs more than 8 seconds.")
        segments = max(math.ceil(distance / .018), math.ceil(angle / .09), 1)
        actuators = self._arm_actuators[arm]
        qpos = self._joint_qpos[actuators]
        plan = [self._data.qpos[qpos].copy()]
        for step in range(1, segments + 1):
            fraction = step / segments
            pose = current * (1 - fraction) + target * fraction
            pose[3:] /= np.linalg.norm(pose[3:])
            q = self._inverse_kinematics(arm, pose, plan[-1])
            if q is None:
                return ActionResult(False, "ik_unreachable", f"No IK solution for waypoint {step}/{segments}.")
            safe = self._verify_joint_segment(arm, qpos, plan[-1], q)
            if safe is not None:
                return ActionResult(False, "collision", f"Planned contact between {safe}.")
            plan.append(q)

        dt = self._model.opt.timestep
        path = list(zip(plan[:-1], plan[1:], strict=True))
        segment_ticks = [
            math.ceil(max(duration / segments, np.max(np.abs(stop - start)) / _MAX_JOINT_SPEED) / dt)
            for start, stop in path
        ]
        settle_ticks = math.ceil(_MOTION_SETTLE_SECONDS / dt)
        if (sum(segment_ticks) + settle_ticks) * dt > _MAX_MOTION_SECONDS:
            return ActionResult(False, "timeout", "Joint limits require more than 8 seconds.")
        for (start, stop), nsteps in zip(path, segment_ticks, strict=True):
            for step in range(1, nsteps + 1):
                self._targets[actuators] = start + (stop - start) * step / nsteps
                self._step_physics()
                if collision := self._unexpected_contact(self._data):
                    self._targets[actuators] = self._data.qpos[qpos]
                    return ActionResult(False, "collision", f"Observed contact between {collision}.")
        for _ in range(settle_ticks):
            self._step_physics()
            if collision := self._unexpected_contact(self._data):
                self._targets[actuators] = self._data.qpos[qpos]
                return ActionResult(False, "collision", f"Observed contact between {collision}.")
        self._mj.mj_forward(self._model, self._data)
        if collision := self._unexpected_contact(self._data):
            self._targets[actuators] = self._data.qpos[qpos]
            return ActionResult(False, "collision", f"Observed contact between {collision}.")
        pose = self._site_pose(self._sites[arm])
        error = np.linalg.norm(np.asarray(pose[:3]) - target[:3])
        angle_error = 2 * math.acos(float(np.clip(abs(np.dot(pose[3:], target[3:])), 0, 1)))
        if error > .006 or angle_error > .07:
            return ActionResult(
                False, "tracking", f"TCP error {error:.4f} m, {angle_error:.3f} rad after settling."
            )
        return ActionResult(True)

    def _verify_joint_segment(self, arm: Arm, qpos: np.ndarray, a: np.ndarray, b: np.ndarray) -> str | None:
        # Ignore static coincidence at the carried cube's old position. After lifting,
        # its load-bearing jaw contacts will be evaluated at its true position during stepping.
        # This is a probe buffer only; the simulated cube remains fully dynamic.
        probe = self._planner_data
        probe.qpos[:] = self._data.qpos
        if self._grasped_by() == arm:
            probe.qpos[self._cube_joint + 2] += 4
        count = max(math.ceil(np.max(np.abs(b - a)) / .06), 1)
        for i in range(1, count + 1):
            probe.qpos[qpos] = a + (b - a) * i / count
            self._mj.mj_fwdPosition(self._model, probe)
            if collision := self._unexpected_contact(probe):
                return collision
        return None

    def _grip(self, arm: Arm, *, opening: bool) -> ActionResult:
        self._ensure_open()
        try:
            arm = validate_arm(arm)
        except ValueError as error:
            return ActionResult(False, "invalid_command", str(error))
        drive = self._drive_actuators[arm]
        initial_goal = self._gripper_goal[arm]
        self._gripper_goal[arm] = self._limits[drive, int(opening)]
        for _ in range(math.ceil(1.16 / self._model.opt.timestep)):
            self._step_physics()
            if collision := self._unexpected_contact(self._data):
                self._gripper_goal[arm] = initial_goal
                return ActionResult(False, "collision", f"Observed contact between {collision}.")
        self._mj.mj_forward(self._model, self._data)
        if opening and not self._is_open(arm):
            return ActionResult(False, "gripper_blocked", "The jaws did not reach the open position.")
        if not opening and self._grasped_by() != arm:
            return ActionResult(False, "empty_grasp", "Both jaw pads must contact the cube.")
        return ActionResult(True)

    def open_gripper(self, arm: Arm) -> ActionResult:
        return self._grip(arm, opening=True)

    def close_gripper(self, arm: Arm) -> ActionResult:
        return self._grip(arm, opening=False)
