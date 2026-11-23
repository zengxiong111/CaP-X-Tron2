"""Serve the TRON2 Cube Lift RGB-D pose estimator over loopback HTTP."""

import argparse
from io import BytesIO
from zipfile import BadZipFile, ZipFile

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from capx.integrations.tron2.backends import ObservationUnavailableError
from capx.integrations.tron2.perception import estimate_tabletop_pose
from capx.integrations.tron2.perception_service import FRAME_FIELDS, SERVICE_NAME

MAX_FRAME_BYTES = 4 * 1024 * 1024
app = FastAPI(title="TRON2 RGB-D perception")


@app.get("/health")
def health():
    return {"service": SERVICE_NAME}


def estimate(payload, name, workspace_z_offset):
    try:
        with ZipFile(BytesIO(payload)) as archive:
            if sum(member.file_size for member in archive.infolist()) > MAX_FRAME_BYTES:
                raise ValueError("Frame arrays are too large")
        with np.load(BytesIO(payload), allow_pickle=False) as arrays:
            frame = {key: arrays[key] for key in FRAME_FIELDS}
        return {"pose": estimate_tabletop_pose(frame, name, workspace_z_offset=workspace_z_offset)}
    except ObservationUnavailableError as error:
        raise HTTPException(422, str(error)) from error
    except (BadZipFile, ValueError, KeyError, TypeError, EOFError) as error:
        raise HTTPException(400, "Invalid RGB-D frame") from error


@app.post("/pose/{name}")
async def pose(request: Request, name: str, workspace_z_offset: float = Query(0.0, ge=-1, le=1)):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > MAX_FRAME_BYTES:
            raise HTTPException(413, "RGB-D frame is too large")
    return await run_in_threadpool(estimate, payload, name, workspace_z_offset)


def serve(port: int = 8121, host: str = "127.0.0.1"):
    """Run the RGB-D service; usable by both YAML launchers and the CLI."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main(port: int | None = None, host: str | None = None):
    if port is not None:
        serve(port=port, host=host or "127.0.0.1")
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8121)
    parser.add_argument("--host", default="127.0.0.1")
    options = parser.parse_args()
    serve(port=options.port, host=options.host)


if __name__ == "__main__":
    main()
