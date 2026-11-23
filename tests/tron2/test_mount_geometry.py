"""Fixed-height MuJoCo mounting geometry checks against the pinned vendor asset."""

import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("TRON2_MJCF_PATH"), reason="requires pinned DACH_TRON2A MJCF")


def _model(path):
    mujoco = pytest.importorskip("mujoco")
    from capx.integrations.tron2.mujoco_backend import _scene

    return mujoco, mujoco.MjModel.from_xml_string(_scene(Path(path)))


def test_fixed_gap_recess_and_support_match_vendor_stand():
    mujoco, model = _model(os.environ["TRON2_MJCF_PATH"])
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    tabletop = model.geom("task_table").pos[2] + model.geom("task_table").size[2]
    base = model.body("base_Link").pos[2]
    assert tabletop == pytest.approx(.620, abs=1e-9)
    assert base == pytest.approx(1.070, abs=1e-9)
    assert base - tabletop == pytest.approx(.450, abs=1e-9)

    stand_meshes = []
    for geom_id in range(model.ngeom):
        body = int(model.geom_bodyid[geom_id])
        if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body) != "base_3_Link":
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        start, count = int(model.mesh_vertadr[mesh_id]), int(model.mesh_vertnum[mesh_id])
        vertices = model.mesh_vert[start:start + count]
        world_vertices = vertices @ data.geom_xmat[geom_id].reshape(3, 3).T + data.geom_xpos[geom_id]
        stand_meshes.append(world_vertices)
    assert stand_meshes
    min_z = min(vertices[:, 2].min() for vertices in stand_meshes)
    assert min_z == pytest.approx(-.13035, abs=2e-5)

    support = model.geom("mount_recess_floor")
    support_top = support.pos[2] + support.size[2]
    assert support_top == pytest.approx(-.12935, abs=1e-9)
    assert support_top - min_z == pytest.approx(.001, abs=2e-5)
    for name in ("ground", "mount_floor_east", "mount_floor_north", "mount_floor_south",
                 "mount_recess_floor", "mount_recess_left_wall", "mount_recess_right_wall",
                 "mount_recess_front_wall", "mount_recess_back_wall"):
        geom = model.geom(name)
        assert model.geom_contype[geom.id] and model.geom_conaffinity[geom.id]


def test_calibrated_overlay_is_not_mounted_twice(tmp_path):
    from capx.integrations.tron2.calibrated_recovery import write_calibrated_mjcf

    vendor = Path(os.environ["TRON2_MJCF_PATH"])
    overlay = tmp_path / "calibrated.xml"
    write_calibrated_mjcf(vendor, overlay)
    _, model = _model(overlay)
    assert model.body("base_Link").pos[2] == pytest.approx(1.070, abs=1e-9)
