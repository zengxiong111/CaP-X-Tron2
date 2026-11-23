"""Experimental fixed-gap DACH_TRON2A mounting and head RGB-D occlusion."""

from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from .recovery_backend import RecoveryMujocoBackend

TABLETOP_Z = 0.620
MOUNT_GAP = 0.450
VENDOR_BASE_Z = 1.210
EXPERIMENT_BASE_Z = TABLETOP_Z + MOUNT_GAP

# Right-arm ready branch verified on the fixed-gap scene at [0.43, -0.22, -0.32] m.
READY = np.array(
    (
        1.50289852223072,
        -2.4200518054276943,
        -0.9494541628289997,
        -1.4767557271848775,
        -0.5400267590736921,
        0.6963559623185722,
        0.883901176474163,
    )
)
# Rounded rectangles in 480 × 360 head-camera pixels, selected on seeds 21–24.
HEAD_PATCHES = ((313, 215, 28, 31), (318, 171, 38, 24), (375, 220, 24, 29))
PATCH_COLOR = (48, 51, 54)
PATCH_RADIUS = 2


def write_calibrated_mjcf(vendor_path: Path, output: Path) -> None:
    """Build an isolated overlay while preserving authored link transforms and meshes."""
    tree = ET.parse(vendor_path)
    compiler = tree.find("compiler")
    base = tree.find("./worldbody/body[@name='base_Link']")
    if compiler is None or base is None:
        raise ValueError("Expected the official DACH_TRON2A gripper XML")
    x, y, z = map(float, base.attrib["pos"].split())
    if not np.isclose(z, VENDOR_BASE_Z, atol=1e-9, rtol=0):
        raise ValueError("Expected the original base_Link at world Z = 1.210 m")
    compiler.set("meshdir", str((vendor_path.parent / compiler.get("meshdir", ".")).resolve()))
    base.set("pos", f"{x:g} {y:g} {EXPERIMENT_BASE_Z:.12g}")
    tree.write(output, encoding="unicode")


def head_mask() -> np.ndarray:
    """Return the fixed rounded rectangle union in native head-camera resolution."""
    yy, xx = np.ogrid[:360, :480]
    mask = np.zeros((360, 480), dtype=bool)
    for cx, cy, width, height in HEAD_PATCHES:
        dx = np.maximum(np.abs(xx - cx) - (width / 2 - PATCH_RADIUS), 0)
        dy = np.maximum(np.abs(yy - cy) - (height / 2 - PATCH_RADIUS), 0)
        mask |= dx**2 + dy**2 <= PATCH_RADIUS**2
    return mask


class CalibratedRecoveryBackend(RecoveryMujocoBackend):
    """Apply the verified ready joint branch and occlude head RGB and depth."""

    def __init__(self, *, model_path: Path, alternate_offsets: bool = False) -> None:
        super().__init__(model_path=model_path, alternate_offsets=alternate_offsets)
        table = self._model.geom("task_table")
        tabletop = table.pos[2] + table.size[2]
        if not np.allclose(
            (tabletop, self._base_pos[2] - tabletop), (TABLETOP_Z, MOUNT_GAP), atol=1e-9, rtol=0
        ):
            self.close()
            raise RuntimeError("Expected the 0.620 m tabletop and 0.450 m mounting gap")
        right = self._arm_actuators["right"]
        self._ready_qpos = self._joint_qpos[right]
        self._ready_dofs = self._joint_dof[right]
        self._right_actuators = right
        limits = self._limits[right]
        if np.any(limits[:, 0] >= READY) or np.any(limits[:, 1] <= READY):
            self.close()
            raise RuntimeError("The calibrated ready pose is outside the right-arm joint limits")
        self._head_mask = head_mask()
        self.trace_seed = None
        self.captures = []
        self.rgb_replays = []
        self.pose_calls = []
        self.pose_cameras = None

    def reset(self, seed=None) -> None:
        super().reset(seed)
        self._data.qpos[self._ready_qpos] = READY
        self._data.qvel[self._ready_dofs] = 0
        self._targets[self._right_actuators] = READY
        self._mj.mj_forward(self._model, self._data)
        self.advance(0.3)
        if contact := self._unexpected_contact(self._data):
            raise RuntimeError(f"Contact at calibrated reset: {contact}")
        self.trace_seed = seed
        self.captures.clear()
        self.rgb_replays.clear()
        self.pose_calls.clear()
        self.pose_cameras = None

    def get_image(self, camera_name):
        if self.pose_cameras is not None:
            self.pose_cameras.append(camera_name)
        frame = super().get_image(camera_name)
        if camera_name != "head":
            return frame
        rgb, depth = frame["rgb"].copy(), frame["depth"].copy()
        rgb[self._head_mask] = PATCH_COLOR
        depth[self._head_mask] = 0
        return {**frame, "rgb": rgb, "depth": depth}

    def raw_head(self):
        """Render the unmasked view for coverage scoring only."""
        return super().get_image("head")
