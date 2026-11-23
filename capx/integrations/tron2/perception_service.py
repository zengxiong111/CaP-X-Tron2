"""Client for the TRON2 tabletop RGB-D perception service."""

from io import BytesIO
from math import isfinite

import numpy as np
import requests

from .backends import CameraFrame, ObservationUnavailableError, Pose

DEFAULT_PERCEPTION_URL = "http://127.0.0.1:8121"
SERVICE_NAME = "tron2-rgbd"
FRAME_FIELDS = ("rgb", "depth", "K", "T_base_camera")


def request_pose(
    url: str,
    frame: CameraFrame,
    name: str,
    workspace_z_offset: float = 0.0,
    *,
    timeout: float = 5.0,
) -> Pose:
    with BytesIO() as stream:
        np.savez(stream, **{key: frame[key] for key in FRAME_FIELDS})
        try:
            response = requests.post(
                f"{url.rstrip('/')}/pose/{name}",
                params={"workspace_z_offset": workspace_z_offset},
                headers={"Content-Type": "application/octet-stream"},
                data=stream.getvalue(),
                timeout=timeout,
            )
            if response.status_code == 422:
                raise ObservationUnavailableError(response.json()["detail"])
            response.raise_for_status()
            pose = tuple(float(value) for value in response.json()["pose"])
            if len(pose) != 7 or not all(map(isfinite, pose)):
                raise ValueError("Invalid pose")
            return pose
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            raise RuntimeError("TRON2 RGB-D perception service request failed") from error
