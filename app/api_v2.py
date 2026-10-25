"""Versioned local API. Original routes remain supported."""

import asyncio
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app import codex_runner, diagnostics, git_utils, planning, repository, verifier
from app.security import redact


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: str = Field(min_length=3, max_length=12000)
    workspace: str = Field(min_length=1, max_length=1024)


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    prompt: str = Field(min_length=3, max_length=24000)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    approved: StrictBool

    @field_validator("approved")
    @classmethod
    def explicit_approval(cls, value):
        if value is not True:
            raise ValueError("Explicit approval is required")
        return value


class ExecutionInput(ApprovalInput):
    max_repairs: int = Field(default=0, ge=0, le=2)


def router(settings, store, workflow):
    routes = APIRouter(prefix="/api/v1", tags=["Operation Famiglia"])

    def workspace(value):
        try:
            return settings.workspace(value)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, redact(str(exc), settings.api_key)) from exc

    def plan_record(plan_id):
        result = store.plan(plan_id)
        if not result:
            raise HTTPException(404, "Plan not found")
        workspace(result["workspace"])
        return result

    def task_record(task_id):
        result = store.get(task_id)
        if not result:
            raise HTTPException(404, "Contract not found")
        return result

    @routes.get("/workspaces/inspect")
    async def inspect_workspace(
        selection: Annotated[str, Query(max_length=1024)],
        request: Annotated[str, Query(max_length=12000)] = "",
    ):
        path = workspace(selection)
        result = await asyncio.to_thread(repository.inspect, path, request)
        branch, status = await asyncio.gather(
            git_utils.git(path, "branch", "--show-current"),
            git_utils.git(path, "status", "--porcelain"),
        )
        result["git"] = {
            "branch": redact(branch.output.strip()),
            "changes": redact(status.output[:16000]),
            "available": branch.code == 0 and status.code == 0,
        }
        return result

    @routes.post("/plans", status_code=201)
    async def create_plan(payload: PlanInput):
        try:
            return await planning.generate(
                payload.request, workspace(payload.workspace), settings, store
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise HTTPException(502, redact(str(exc), settings.api_key)) from exc

    @routes.get("/plans/{plan_id}")
    async def get_plan(plan_id: str):
        return plan_record(plan_id)

    @routes.post("/plans/{plan_id}/revisions")
    async def revise(plan_id: str, payload: RevisionInput):
        plan_record(plan_id)
        try:
            return store.revise_plan(
                plan_id, payload.revision, redact(payload.prompt, settings.api_key)
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @routes.post("/plans/{plan_id}/approve")
    async def approve(plan_id: str, payload: ApprovalInput):
        plan_record(plan_id)
        try:
            return store.approve_plan(plan_id, payload.revision)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @routes.post("/plans/{plan_id}/execute", status_code=201)
    async def execute(plan_id: str, payload: ExecutionInput):
        record = plan_record(plan_id)
        try:
            task_id = await workflow.start(
                record["request"],
                record["prompt"],
                workspace(record["workspace"]),
                plan_id=plan_id,
                revision=payload.revision,
                max_repairs=payload.max_repairs,
            )
        except ValueError as exc:
            raise HTTPException(409, redact(str(exc), settings.api_key)) from exc
        except (OSError, TimeoutError) as exc:
            raise HTTPException(503, redact(str(exc), settings.api_key)) from exc
        return {**task_record(task_id), "execution": store.execution(task_id)}

    @routes.get("/tasks/{task_id}/execution")
    async def execution(task_id: str):
        task_record(task_id)
        return store.execution(task_id)

    @routes.get("/tasks/{task_id}/logs")
    async def logs(task_id: str, after: int = Query(0, ge=0)):
        task_record(task_id)
        events = store.events(task_id, after)
        return {"events": events, "next_cursor": events[-1]["id"] if events else after}

    @routes.get("/tasks")
    async def history(
        limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=100000)
    ):
        with store.connection() as db:
            total = db.execute("SELECT count(*) FROM tasks").fetchone()[0]
            rows = db.execute(
                "SELECT * FROM tasks ORDER BY started_at DESC,id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return {
            "items": [store.decode(row) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @routes.get("/system/readiness")
    async def readiness():
        codex, isolation = await asyncio.gather(
            codex_runner.availability(settings), verifier.availability(settings)
        )
        with store.connection() as db:
            database = db.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "status": "ready" if codex["available"] and isolation["available"] else "BLOCKED",
            "database": database,
            "codex": codex,
            "verification": isolation,
            "startup": "uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765",
            "source_root": str(Path(__file__).resolve().parent.parent),
        }

    @routes.get("/memory")
    async def memories(selection: Annotated[str, Query(max_length=1024)]):
        path = workspace(selection)
        signature = await asyncio.to_thread(repository.fingerprint, path)
        return {"items": store.memories(str(path), signature), "fingerprint": signature}

    @routes.delete("/memory/{memory_id}")
    async def forget(memory_id: str, selection: Annotated[str, Query(max_length=1024)]):
        path = workspace(selection)
        if not store.forget(memory_id, str(path)):
            raise HTTPException(404, "Memory not found in this workspace")
        return {"deleted": True}

    @routes.get("/system/diagnostics")
    async def system_diagnostics():
        return await diagnostics.report(settings)

    @routes.get("/github/status")
    async def github_status():
        return await diagnostics.github_status()

    @routes.get("/tasks/{task_id}/pr-report")
    async def pr_report(task_id: str):
        task = task_record(task_id)
        execution = store.execution(task_id)
        return {
            "task_id": task_id,
            "remote_write": False,
            "title": task["request"][:120],
            "body": (
                f"Requirement: {task['request']}\n\n"
                f"Verdict: {task['status']}; Codex exit: {task['exit_code']}\n\n"
                "Modified files:\n"
                + "\n".join(task["changed_files"])
                + "\n\nVerification:\n"
                + str(task["verification"])
                + "\n\nReview and security evidence:\n"
                + str(execution["evidence"][-3:])
                + "\n\nHuman review: inspect requirements, diff, tests and unresolved findings.\n"
                "Commit, push and PR publication require separate authorization."
            ),
        }

    return routes
