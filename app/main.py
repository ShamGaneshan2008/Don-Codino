"""Local-only FastAPI interface. Run one worker, bound to 127.0.0.1."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import codex_runner, planning, verifier
from app.api_v2 import router
from app.config import Settings
from app.database import Store
from app.locks import lease
from app.request_limits import RequestLimits
from app.security import redact
from app.workflow import STAGES, Workflow

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=12000)]


class PromptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: Text
    workspace: Annotated[str, Field(min_length=1, max_length=1024)]


class TaskInput(PromptInput):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=24000)]
    approved: Literal[True]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.database)
    workflow = Workflow(settings, store)

    @asynccontextmanager
    async def lifespan(_app):
        with lease(settings.database.with_suffix(".server.lock")):
            store.recover()
            try:
                yield
            finally:
                await workflow.shutdown()

    app = FastAPI(
        title="Don Codino",
        version="0.2.0-alpha.1",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.store, app.state.workflow = store, workflow
    # These routes have no nested lifespan/dependencies. Attach concrete APIRoutes
    # to preserve application.routes introspection on both old and new FastAPI.
    app.router.routes.extend(router(settings, store, workflow).routes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.add_middleware(RequestLimits)

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin and origin != expected:
            return JSONResponse(
                {"detail": "Cross-origin requests are not allowed."}, status_code=403
            )
        if request.method == "POST" and not request.headers.get("content-type", "").startswith(
            "application/json"
        ):
            return JSONResponse({"detail": "application/json is required."}, status_code=415)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def workspace(value: str) -> Path:
        try:
            return settings.workspace(value)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def task(task_id: str):
        found = store.get(task_id)
        if not found:
            raise HTTPException(404, "Contract not found.")
        return found

    @app.get("/health")
    async def health():
        return {"status": "ok", "application": "Don Codino"}

    @app.get("/api/workspaces")
    async def workspaces():
        return {
            "workspace_root": str(settings.workspace_root),
            "workspaces": settings.discover_workspaces(),
        }

    @app.get("/api/settings")
    async def configuration():
        codex, isolation = await asyncio.gather(
            codex_runner.availability(settings),
            verifier.availability(settings),
        )
        return {
            "workspace_root": str(settings.workspace_root),
            "workspaces": settings.discover_workspaces(),
            "codex": {**codex, "message": redact(codex["message"], settings.api_key)},
            "verification": isolation,
            "timeout_seconds": settings.timeout_seconds,
            "prompt_mode": "openai" if settings.api_key and settings.model else "template",
            "stages": STAGES,
        }

    @app.post("/api/prompts/enhance")
    async def enhance(payload: PromptInput):
        path = workspace(payload.workspace)
        try:
            result = await planning.generate(payload.request, path, settings, store)
            result["prompt"] = redact(result["prompt"], settings.api_key)
            return result
        except (httpx.HTTPError, ValueError, OSError) as exc:
            raise HTTPException(
                502,
                "Prompt refinement failed: "
                + redact(
                    str(exc),
                    settings.api_key,
                ),
            ) from exc

    @app.post("/api/tasks", status_code=201)
    async def start(payload: TaskInput):
        path = workspace(payload.workspace)
        try:
            task_id = await workflow.start(payload.request, payload.prompt, path)
        except ValueError as exc:
            raise HTTPException(409, redact(str(exc), settings.api_key)) from exc
        except (OSError, TimeoutError) as exc:
            raise HTTPException(
                503,
                "Workspace preflight unavailable: " + redact(str(exc), settings.api_key),
            ) from exc
        return task(task_id)

    @app.get("/api/tasks")
    async def history(limit: int = Query(50, ge=1, le=100)):
        return store.list(limit)

    @app.get("/api/tasks/{task_id}")
    async def detail(task_id: str):
        return {**task(task_id), "execution": store.execution(task_id)}

    @app.get("/api/tasks/{task_id}/diff")
    async def diff(task_id: str):
        found = task(task_id)
        return {"files": found["changed_files"], "diff": found["diff"]}

    @app.get("/api/tasks/{task_id}/events")
    async def events(task_id: str, request: Request, after: int = Query(0, ge=0)):
        task(task_id)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError as exc:
            raise HTTPException(400, "Invalid event cursor") from exc

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                batch = store.events(task_id, cursor)
                for event in batch:
                    cursor = event["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                # Drain again after every emitted batch: the producer can finish while
                # the response yields, adding a verdict after the first database read.
                if batch:
                    continue
                if task(task_id)["status"] != "RUNNING":
                    yield "event: done\ndata: {}\n\n"
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.4)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel(task_id: str):
        task(task_id)
        return {"cancellation_requested": workflow.cancel(task_id)}

    static = Path(__file__).parent / "static"

    @app.get("/")
    async def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
