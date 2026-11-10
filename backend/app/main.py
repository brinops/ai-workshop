"""FastAPI application: API + SSE + built dashboard + embedded worker loop."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes, stream, training_jira, workshop_pairing, workshop_runs
from app.config import REPO_ROOT, get_settings
from app.control_plane import get_config
from app.db import init_engine, run_migrations
from app.integrations.slack_socket import run_socket_mode
from app.orchestration.worker import Worker

log = logging.getLogger("rcp")
DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = get_config()  # fail fast on a broken control-plane.yaml
    log.info("control-plane.yaml: %s", ", ".join(f"{r.repo} ({len(r.routes)} route(s))" for r in cfg.repositories))
    run_migrations()
    init_engine()
    worker_job = None
    if s.run_worker:
        worker = Worker()
        app.state.worker = worker
        worker_job = asyncio.create_task(worker.run_forever(), name="rcp-worker")
    socket_job = None
    if s.workshop_slack_app_token and s.workshop_slack_workspace_id:
        socket_job = asyncio.create_task(run_socket_mode(
            s.workshop_slack_app_token.get_secret_value(), s.workshop_slack_workspace_id,
        ), name="workshop-slack-socket")
    try:
        yield
    finally:
        if socket_job:
            socket_job.cancel()
            with suppress(asyncio.CancelledError):
                await socket_job
        if worker_job:
            app.state.worker.stop()
            await asyncio.wait_for(worker_job, timeout=30)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="CI Control Plane", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(routes.router)
    app.include_router(stream.router)
    app.include_router(training_jira.router)
    app.include_router(workshop_pairing.router)
    app.include_router(workshop_runs.router)

    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (DIST / path).resolve()
            if path and candidate.is_file() and DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(DIST / "index.html")

    return app


app = create_app()
