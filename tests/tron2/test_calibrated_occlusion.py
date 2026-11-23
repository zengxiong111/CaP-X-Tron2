from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from capx.envs.evaluate_tron2_calibrated_occlusion import archived_rgb_replay, sha256
from capx.envs.evaluate_tron2_recovery import encode_rgb
from capx.integrations.tron2.calibrated_recovery import head_mask, write_calibrated_mjcf


def test_calibrated_overlay_leaves_vendor_source_untouched(tmp_path):
    source = tmp_path / "vendor.xml"
    original = (
        '<mujoco><compiler meshdir="../meshes" /><worldbody>'
        '<body name="base_Link" pos="0 0 1.21">'
        '<body name="base_3_Link" pos="0 0 -0.9295" />'
        "</body></worldbody></mujoco>"
    )
    source.write_text(original)
    overlay = tmp_path / "calibrated.xml"
    write_calibrated_mjcf(source, overlay)
    root = ET.parse(overlay).getroot()
    assert source.read_text() == original
    assert root.find(".//body[@name='base_Link']").get("pos") == "0 0 1.07"
    assert root.find(".//body[@name='base_3_Link']").get("pos") == "0 0 -0.9295"
    assert Path(root.find("compiler").get("meshdir")) == tmp_path.parent / "meshes"


def test_head_mask_matches_the_recorded_geometry():
    mask = head_mask()
    assert mask.shape == (360, 480)
    assert mask.sum() == 2571
    assert mask[215, 313] and mask[171, 318] and mask[220, 375]
    assert not mask[20, 20]


def test_archived_rgb_replay_accepts_rounding_and_rejects_red_mask_change():
    reference = np.zeros((8, 8, 3), dtype=np.uint8)
    reference[1, 1] = [100, 10, 10]
    saved = encode_rgb({"rgb": reference})

    rgb = reference.copy()
    rgb[0, 0, 1] = 1
    replay = archived_rgb_replay(rgb, encode_rgb({"rgb": rgb}), saved, sha256(saved))
    assert replay["same_red_masks"]
    assert replay["changed_pixels_in_live_render"] == 1

    rgb[1, 1, 0] = 101
    with pytest.raises(RuntimeError, match="red masks match False"):
        archived_rgb_replay(rgb, encode_rgb({"rgb": rgb}), saved, sha256(saved))
