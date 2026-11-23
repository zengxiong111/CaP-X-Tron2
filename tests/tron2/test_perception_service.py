from io import BytesIO

import numpy as np
import pytest
from fastapi import HTTPException

from capx.integrations.tron2.perception_service import FRAME_FIELDS, request_pose
from capx.serving.launch_tron2_rgbd_server import estimate


def test_service_uses_calibrated_workspace_offset(monkeypatch):
    intrinsics = np.array([[600, 0, 8], [0, 600, 8], [0, 0, 1]])
    transform = np.eye(4)
    transform[:3, 3] = (0.45, -0.18, -0.75)
    frame = {
        "rgb": np.full((17, 17, 3), (230, 20, 20), dtype=np.uint8),
        "depth": np.full((17, 17), 0.49, dtype=np.float32),
        "K": intrinsics,
        "T_base_camera": transform,
    }
    with BytesIO() as stream:
        np.savez(stream, **{key: frame[key] for key in FRAME_FIELDS})
        with pytest.raises(HTTPException) as error:
            estimate(stream.getvalue(), "cube", 0)
    assert error.value.status_code == 422

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def post(url, *, params, headers, data, timeout):
        assert url == "http://127.0.0.1:8121/pose/cube"
        assert headers["Content-Type"] == "application/octet-stream"
        return Response(estimate(data, "cube", params["workspace_z_offset"]))

    monkeypatch.setattr("capx.integrations.tron2.perception_service.requests.post", post)
    pose = request_pose("http://127.0.0.1:8121", frame, "cube", 0.14)
    assert pose == pytest.approx((0.45, -0.18, -0.28, 1, 0, 0, 0))
