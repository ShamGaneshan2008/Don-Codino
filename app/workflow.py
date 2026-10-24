"""Task orchestration with persisted stages and one active writer per workspace."""

import asyncio
import sqlite3
from pathlib import Path

from app import codex_runner, git_utils, verifier
from app.config import Settings
from app.database import Store, now
from app.security import redact, sanitize

STAGES = ["The Meeting", "The Plan", "The Hitman", "The Cleanup", "The Inspection", "The Verdict"]


class Workflow:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.active: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    async def start(self, request: str, prompt: str, workspace: Path) -> str:
        # This runs on one event loop; the partial unique DB index also enforces the lock.
        if any(self.store.get(task_id)["workspace"] == str(workspace) for task_id in self.active):
            raise ValueError("A contract is already running in this workspace.")
        await git_utils.require_clean(workspace)
        try:
            task_id = self.store.create(
                redact(request, self.settings.api_key),
                redact(prompt, self.settings.api_key),
                str(workspace),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A contract is already running in this workspace.") from exc
        cancel = asyncio.Event()
        task = asyncio.create_task(self.run(task_id, workspace, prompt, cancel))
        self.active[task_id] = (task, cancel)
        return task_id

    def event(self, task_id: str, kind: str, text: str):
        self.store.event(task_id, kind, redact(text, self.settings.api_key))

    def stage(self, task_id: str, number: int):
        self.store.update(task_id, stage=number)
        self.event(task_id, "stage", STAGES[number])

    async def run(self, task_id: str, workspace: Path, prompt: str, cancel: asyncio.Event):
        status, message = "BLOCKED", "Execution did not complete."
        try:
            self.stage(task_id, 0)
            # Revalidate immediately before subprocess execution.
            if self.settings.workspace(str(workspace)) != workspace:
                raise ValueError("Workspace changed since approval.")
            await git_utils.require_clean(workspace)
            self.stage(task_id, 1)
            self.event(task_id, "info", "The edited plan was approved for this workspace.")
            ready = await codex_runner.availability(self.settings)
            if cancel.is_set():
                raise asyncio.CancelledError
            if not ready["available"]:
                message = "Our associate Codex is unavailable. " + ready["message"]
                return
            self.stage(task_id, 2)
            result = await codex_runner.execute(
                self.settings,
                workspace,
                prompt,
                cancel,
                lambda text: self.event(task_id, "codex", text),
            )
            self.store.update(task_id, exit_code=result.code)
            if cancel.is_set():
                raise asyncio.CancelledError
            if result.code:
                status, message = "FAIL", f"Codex exited with status {result.code}."
                return
            self.stage(task_id, 3)
            report = await verifier.verify(
                self.settings,
                workspace,
                cancel,
                lambda text: self.event(task_id, "verification", text),
            )
            if cancel.is_set():
                raise asyncio.CancelledError
            report = sanitize(report, self.settings.api_key)
            self.store.update(task_id, verification=report)
            status = report["status"]
            message = {
                "PASS": "Business is concluded, Boss.",
                "FAIL": "Someone left fingerprints in the code.",
                "BLOCKED": "Verification is blocked. Review the evidence.",
            }[status]
        except asyncio.CancelledError:
            status, message = "CANCELLED", "Contract cancelled. Partial changes may remain."
        except (OSError, ValueError, TimeoutError) as exc:
            message = redact(str(exc), self.settings.api_key)
        except Exception as exc:
            status, message = (
                "FAIL",
                "Unexpected workflow error: "
                + redact(
                    str(exc),
                    self.settings.api_key,
                ),
            )
        finally:
            try:
                self.stage(task_id, 4)
                files, diff = await git_utils.inspect(workspace)
                self.store.update(
                    task_id,
                    changed_files=files,
                    diff=redact(diff, self.settings.api_key),
                )
                if status == "PASS" and not files:
                    status, message = "BLOCKED", "Our associate returned empty-handed."
            except (OSError, ValueError, TimeoutError) as exc:
                if status == "PASS":
                    status = "BLOCKED"
                message += " Git inspection failed: " + redact(str(exc), self.settings.api_key)
            self.stage(task_id, 5)
            self.event(task_id, "verdict", message)
            self.store.update(
                task_id,
                status=status,
                message=redact(message, self.settings.api_key),
                ended_at=now(),
            )
            self.active.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        item = self.active.get(task_id)
        if not item:
            return False
        item[1].set()
        return True

    async def shutdown(self):
        tasks = list(self.active.values())
        for _, cancel in tasks:
            cancel.set()
        if tasks:
            await asyncio.gather(*(task for task, _ in tasks), return_exceptions=True)
