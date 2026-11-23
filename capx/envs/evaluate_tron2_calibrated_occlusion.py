"""Run the TRON2 fixed-gap head-occlusion experiment with the paired evaluator."""

import argparse
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PIL import Image

from capx.envs import evaluate_tron2_recovery as evaluation
from capx.integrations.tron2 import perception
from capx.integrations.tron2.backends import ObservationUnavailableError
from capx.integrations.tron2.calibrated_recovery import (
    EXPERIMENT_BASE_Z,
    HEAD_PATCHES,
    MOUNT_GAP,
    TABLETOP_Z,
    VENDOR_BASE_Z,
    CalibratedRecoveryBackend,
    write_calibrated_mjcf,
)
from capx.integrations.tron2.perception_service import request_pose
from capx.integrations.tron2.target_motion import red_target_mask

WORKSPACE_Z_SHIFT = round(VENDOR_BASE_Z - EXPERIMENT_BASE_Z, 3)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def archived_rgb_replay(rgb, image, archived, expected_hash):
    """Allow minor EGL rounding only when both target classifications stay exact."""
    if sha256(archived) != expected_hash:
        raise RuntimeError("The archived baseline image does not match its recorded hash")
    with Image.open(BytesIO(archived)) as png:
        reference = np.asarray(png.convert("RGB"), dtype=np.int16)
    if reference.shape != rgb.shape:
        raise RuntimeError("The live and archived RGB image sizes differ")
    delta = np.abs(reference - rgb.astype(np.int16))
    changed_pixels = int(np.any(delta, axis=2).sum())
    max_delta = int(delta.max())
    same_masks = all(
        np.array_equal(classify(reference), classify(rgb))
        for classify in (red_target_mask, perception.cube_color_mask)
    )
    if changed_pixels > 16 or max_delta > 1 or not same_masks:
        raise RuntimeError(
            f"Live RGB differs from the baseline: {changed_pixels} pixels, "
            f"max channel difference {max_delta}, red masks match {same_masks}"
        )
    return {
        "changed_pixels_in_live_render": changed_pixels,
        "max_live_rgb_channel_delta": max_delta,
        "same_red_masks": same_masks,
        "live_render_sha256": sha256(image),
    }


class OcclusionEnv(evaluation.Tron2MujocoEnv):
    """Record the camera path for the existing S2 pose tool."""

    def __init__(self, *, perception_url=None, **kwargs):
        super().__init__(**kwargs)
        self._perception_url = perception_url

    def _estimate_pose(self, frame, name):
        if self._perception_url:
            return request_pose(self._perception_url, frame, name, WORKSPACE_Z_SHIFT)
        return perception.estimate_tabletop_pose(frame, name, workspace_z_offset=WORKSPACE_Z_SHIFT)

    def get_object_pose(self, name):
        record = {"name": name, "cameras": [], "success": False}
        self._backend.pose_cameras = record["cameras"]
        try:
            pose = super().get_object_pose(name)
            record["success"] = True
            return pose
        except ObservationUnavailableError as error:
            record["failure"] = str(error)
            raise
        finally:
            self._backend.pose_cameras = None
            self._backend.pose_calls.append(record)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Pass the remaining options from python -m capx.envs.evaluate_tron2_recovery.",
        allow_abbrev=False,
    )
    parser.add_argument("--baseline", type=Path, help="Text report from this experiment")
    parser.add_argument("--perception-url", help="TRON2 RGB-D pose service base URL")
    parser.add_argument("--record-overview", action="store_true", help="Save final overview frames")
    options, evaluator_args = parser.parse_known_args()
    if any(arg == "--camera" or arg.startswith("--camera=") for arg in evaluator_args):
        parser.error("The experiment uses the default head camera")
    vendor = os.environ.get("TRON2_MJCF_PATH")
    if not vendor or not Path(vendor).is_file():
        parser.error("Set TRON2_MJCF_PATH to the original DACH_TRON2A gripper XML")
    vendor_path = Path(vendor).resolve()
    metadata = {
        "profile": "fixed_gap_head_occlusion_v1",
        "tabletop_world_z_m": TABLETOP_Z,
        "base_link_world_z_m": EXPERIMENT_BASE_Z,
        "base_to_table_gap_m": MOUNT_GAP,
        "vendor_mjcf_sha256": sha256(vendor_path.read_bytes()),
        "head_patches_center_xy_width_height": [list(spec) for spec in HEAD_PATCHES],
    }
    if options.perception_url:
        metadata["perception_url"] = options.perception_url
    baseline_rows = {}
    if options.baseline:
        baseline = json.loads(options.baseline.read_text(encoding="utf-8"))
        if baseline.get("local_experiment") != metadata:
            parser.error("The text baseline must use this mounting and occlusion experiment")
        baseline_rows = {row["seed"]: row for row in baseline["seed_results"]}
        evaluator_args.extend(["--baseline", str(options.baseline)])

    active = None
    original_encode = evaluation.encode_rgb
    original_execute = evaluation.execute
    original_write = evaluation.write_report
    recorded_overview = set()

    def make_backend(**kwargs):
        nonlocal active
        active = CalibratedRecoveryBackend(model_path=overlay_path, **kwargs)
        return active

    def execute(env, backend, generation):
        previous_calls = len(backend.pose_calls)
        turn = original_execute(env, backend, generation)
        turn["pose_api_calls"] = backend.pose_calls[previous_calls:]
        return turn

    def encode(frame):
        reference = active.raw_head()
        visible = int(red_target_mask(frame["rgb"]).sum())
        total = int(red_target_mask(reference["rgb"]).sum())
        depth_hash = sha256(frame["depth"].tobytes())
        index = len(active.captures)
        active.captures.append(
            {
                "visible_red_px": visible,
                "reference_red_px": total,
                "hidden_red_fraction": (total - visible) / total if total else None,
                "depth_sha256": depth_hash,
                "pixels_invalidated": int(
                    ((frame["depth"] == 0) & (reference["depth"] != 0)).sum()
                ),
            }
        )
        image = original_encode(frame)
        seed = active.trace_seed
        if seed in baseline_rows:
            row = baseline_rows[seed]
            if depth_hash != row["head_captures"][index]["depth_sha256"]:
                raise RuntimeError(f"Seed {seed} does not match the text arm's depth image")
            expected = row["frame_sha256"][index]
            if sha256(image) != expected:
                phase = ("before", "after")[index]
                frame_dir = options.baseline.with_name(options.baseline.stem + "_frames")
                archived = (frame_dir / f"{seed:02d}_{phase}.png").read_bytes()
                replay = archived_rgb_replay(frame["rgb"], image, archived, expected)
                active.rgb_replays.append({"phase": phase, **replay})
                image = archived
        return image

    def write_report(report, output):
        report["local_experiment"] = metadata
        row = report["seed_results"][-1]
        row["head_captures"] = list(active.captures)
        row["archived_rgb_replays"] = list(active.rgb_replays)
        if options.record_overview and row["seed"] not in recorded_overview:
            frame_dir = output.with_name(output.stem + "_frames")
            frame = original_encode(active.get_image("overview"))
            (frame_dir / f"{row['seed']:02d}_overview.png").write_bytes(frame)
            recorded_overview.add(row["seed"])
        original_write(report, output)

    with (
        TemporaryDirectory(prefix="capx-tron2-occlusion-") as directory,
        patch.object(evaluation, "RecoveryMujocoBackend", make_backend),
        patch.object(
            evaluation,
            "Tron2MujocoEnv",
            lambda **kwargs: OcclusionEnv(perception_url=options.perception_url, **kwargs),
        ),
        patch.object(evaluation, "execute", execute),
        patch.object(evaluation, "encode_rgb", encode),
        patch.object(evaluation, "write_report", write_report),
    ):
        overlay_path = Path(directory) / "robot_grasper.xml"
        write_calibrated_mjcf(vendor_path, overlay_path)
        evaluation.main(evaluator_args)


if __name__ == "__main__":
    main()
