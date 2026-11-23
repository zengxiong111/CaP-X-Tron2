"""Manage the local TRON2 perception and evaluation processes for the web UI."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from capx.integrations.tron2.perception_service import DEFAULT_PERCEPTION_URL, SERVICE_NAME
from capx.llm.client import ModelQueryArgs, query_model

ROOT = Path(__file__).resolve().parents[2]
PERCEPTION_MODULE = "capx.serving.launch_tron2_rgbd_server"
EVALUATION_MODULE = "capx.envs.evaluate_tron2_recovery"
OCCLUSION_MODULE = "capx.envs.evaluate_tron2_calibrated_occlusion"
TASK_CONFIGS = {
    "cube_lift": "env_configs/tron2/cube_lift_s2_guided.yaml",
    "pick_place": "env_configs/tron2/pick_place_s2_guided.yaml",
}


class EvaluationSettings(BaseModel):
    model: str | None = Field(default=None, max_length=200)
    server_url: str | None = Field(default=None, max_length=500)
    start_seed: int = Field(default=41, ge=1)
    trials: int = Field(default=1, ge=1)
    task: Literal["cube_lift", "pick_place"] = "cube_lift"
    feedback: Literal["oracle", "single", "text", "vdm"] = "text"
    occlusion: bool = True


class ModelSettings(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    server_url: str = Field(min_length=1, max_length=500)


def validate_model_endpoint(settings):
    if not (settings.server_url and settings.model):
        raise HTTPException(422, "Provide the model ID and its Chat Completions endpoint.")
    try:
        endpoint = urlsplit(settings.server_url)
        port = endpoint.port
    except ValueError:
        endpoint, port = None, None
    if (
        endpoint is None
        or endpoint.scheme != "http"
        or endpoint.hostname not in ("localhost", "127.0.0.1", "::1")
        or port is None
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
        or not endpoint.path.endswith("/chat/completions")
    ):
        raise HTTPException(
            422, "Use a loopback HTTP Chat Completions endpoint with an explicit port."
        )


def check_perception():
    try:
        response = requests.get(f"{DEFAULT_PERCEPTION_URL}/health", timeout=0.5)
        return response.ok and response.json().get("service") == SERVICE_NAME
    except (requests.RequestException, ValueError, AttributeError):
        return False


def spawn(module, *args, log=None):
    env = {**os.environ, "MUJOCO_GL": "egl", "PYTHONUNBUFFERED": "1"}
    cmd = [sys.executable, "-m", module, *args]
    if log is None:
        return subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, env=env)
    with log.open("w", encoding="utf-8") as stream:
        return subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )


async def stop_process(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, 4)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait)


def local_client(request: Request) -> None:
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Open the TRON2 workflow from the simulator computer.")


class EvaluationRun:
    def __init__(self, settings, directory):
        self.settings = settings
        self.directory = directory
        self.stopped = False
        self.report = directory / "result.json"
        self.baseline = directory / "baseline.json"
        self._followup_error = None
        self.stage = "baseline" if settings.feedback == "vdm" else settings.feedback
        self.process = self._spawn(self.stage)
        self.followup = (
            asyncio.create_task(self._run_vdm_after_baseline())
            if settings.feedback == "vdm"
            else None
        )

    def _spawn(self, stage):
        settings = self.settings
        module = OCCLUSION_MODULE if settings.occlusion else EVALUATION_MODULE
        path = self.baseline if stage == "baseline" else self.report
        self.log = path.with_suffix(".log")
        flags = (
            ["--oracle"]
            if stage == "oracle"
            else ["--model", settings.model, "--server-url", settings.server_url, "--fail-fast-model"]
        )
        if stage == "single":
            flags.append("--single-turn")
        elif stage == "vdm":
            flags.extend(["--baseline", str(self.baseline), "--target-motion"])
        return spawn(
            module,
            "--config",
            TASK_CONFIGS[settings.task],
            "--start-seed",
            str(settings.start_seed),
            "--trials",
            str(settings.trials),
            "--offset-directions",
            "+X,-Y",
            "--perception-url",
            DEFAULT_PERCEPTION_URL,
            "--record-overview",
            "--output",
            str(path),
            *flags,
            log=self.log,
        )

    async def _run_vdm_after_baseline(self):
        code = await asyncio.to_thread(self.process.wait)
        if code == 0 and not self.stopped:
            try:
                self.process = self._spawn("vdm")
            except OSError as error:
                self._followup_error = str(error)
            else:
                self.stage = "vdm"

    @property
    def running(self):
        return not self.stopped and (
            self.process.poll() is None or (self.followup is not None and not self.followup.done())
        )

    async def stop(self):
        self.stopped = True
        await stop_process(self.process)
        if self.followup is not None:
            await self.followup

    def status(self):
        rc = self.process.poll()
        active_report = self.baseline if self.stage == "baseline" else self.report
        report = json.loads(active_report.read_text()) if active_report.exists() else {}
        rows = report.get("seed_results", [])
        successful = sum(
            row["initial"]["task_completed"] or (row["recovery"] or {}).get("task_completed", False)
            for row in rows
        )
        state = (
            "stopped"
            if self.stopped
            else "error"
            if self._followup_error
            else "running"
            if self.running
            else "complete"
            if rc == 0
            else "error"
        )
        error = self._followup_error
        if state == "error" and error is None:
            with self.log.open("rb") as stream:
                stream.seek(max(self.log.stat().st_size - 4096, 0))
                lines = stream.read().decode(errors="replace").strip().splitlines()
            error = lines[-1][-400:] if lines else f"Evaluation exited with code {rc}."
        result = {
            "state": state,
            "id": self.directory.name,
            "total": self.settings.trials,
            "completed": len(rows),
            "successes": successful,
            "task": self.settings.task,
            "stage": self.stage,
            "baseline_successes": None,
            "visual_directions": report.get("summary", {}).get("correct_visual_directions"),
            "latest": None,
            "error": error,
        }
        if self.stage == "vdm" and self.baseline.exists():
            baseline = json.loads(self.baseline.read_text())
            result["baseline_successes"] = baseline.get("summary", {}).get("final_successes")
        if rows:
            row = rows[-1]
            initial, recovery = row["initial"], row["recovery"]
            result["latest"] = {
                "seed": row["seed"],
                "failure": (initial["failure_reason"] or {}).get("code"),
                "lift_cm": (recovery or {}).get("physical_lift_cm"),
                "code": (recovery or initial)["generation"]["program"],
                "pose_requests": sum(
                    calls if isinstance(calls, int) else len(calls)
                    for calls in (t.get("pose_api_calls", []) for t in (initial, recovery) if t)
                ),
                "frames": {
                    phase: f"/api/tron2/frame/{self.directory.name}/{active_report.stem}/{row['seed']}/{phase}"
                    for phase in ("before", "after", "overview")
                },
            }
        return result


def register_tron2_workflow(app: FastAPI):
    router = APIRouter(prefix="/api/tron2", dependencies=[Depends(local_client)])
    lock = asyncio.Lock()
    perception_process = None
    run = None

    @router.get("/status")
    async def status():
        return {
            "perception": await asyncio.to_thread(check_perception),
            "owned_perception": perception_process is not None
            and perception_process.poll() is None,
            "run": run.status() if run else None,
        }

    @router.post("/perception/start")
    async def start_perception():
        nonlocal perception_process
        async with lock:
            if not await asyncio.to_thread(check_perception):
                if perception_process is None or perception_process.poll() is not None:
                    perception_process = spawn(PERCEPTION_MODULE)
                for _ in range(30):
                    if await asyncio.to_thread(check_perception):
                        break
                    if perception_process.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                else:
                    await stop_process(perception_process)
            if not await asyncio.to_thread(check_perception):
                raise HTTPException(503, "Unable to start TRON2 RGB-D perception on port 8121.")
        return await status()

    @router.post("/perception/stop")
    async def stop_perception():
        async with lock:
            await stop_process(perception_process)
        return await status()

    @router.post("/model/check")
    async def check_model(settings: ModelSettings):
        validate_model_endpoint(settings)
        args = ModelQueryArgs(
            model=settings.model,
            server_url=settings.server_url,
            temperature=0,
            max_tokens=8,
            request_timeout=15,
            max_server_retries=0,
            use_configured_url=True,
        )
        try:
            reply = await asyncio.to_thread(
                query_model, args, [{"role": "user", "content": "Reply with OK."}]
            )
            if not reply["content"].strip():
                raise ValueError("Empty response")
        except requests.HTTPError as error:
            raise HTTPException(
                502, f"The model endpoint returned HTTP {error.response.status_code}."
            ) from error
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RuntimeError,
        ) as error:
            raise HTTPException(
                502, "Could not get a response from the configured model."
            ) from error
        return {"model": settings.model, "server_url": settings.server_url}

    @router.post("/evaluation/start")
    async def start_evaluation(settings: EvaluationSettings):
        nonlocal run
        if settings.feedback != "oracle":
            validate_model_endpoint(settings)
        async with lock:
            if run and run.running:
                raise HTTPException(409, "A TRON2 evaluation is already running.")
            if not await asyncio.to_thread(check_perception):
                raise HTTPException(503, "Start the TRON2 RGB-D perception server first.")
            vendor = os.environ.get("TRON2_MJCF_PATH")
            if not vendor or not Path(vendor).is_file():
                raise HTTPException(
                    400, "Set TRON2_MJCF_PATH to the original DACH_TRON2A gripper XML."
                )
            output = Path(os.environ.get("CAPX_TRON2_OUTPUT_DIR", ROOT / "outputs/tron2_web"))
            output.mkdir(parents=True, exist_ok=True)
            run = EvaluationRun(settings, Path(mkdtemp(prefix="run-", dir=output)).resolve())
        return await status()

    @router.post("/evaluation/stop")
    async def stop_evaluation():
        async with lock:
            if run and run.running:
                await run.stop()
        return await status()

    @router.get("/frame/{run_id}/{arm}/{seed}/{phase}")
    async def get_frame(run_id: str, arm: Literal["baseline", "result"], seed: int, phase: str):
        if not run or run.directory.name != run_id or phase not in ("before", "after", "overview"):
            raise HTTPException(404, "Frame not found.")
        image = run.directory / f"{arm}_frames" / f"{seed:02d}_{phase}.png"
        if not image.is_file():
            raise HTTPException(404, "Frame not found.")
        return FileResponse(image, media_type="image/png")

    async def close():
        if run:
            await run.stop()
        await stop_process(perception_process)

    app.include_router(router)
    return close
