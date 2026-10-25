"""Task orchestration with persisted stages and one active writer per workspace."""

import asyncio
import sqlite3
from pathlib import Path

from app import check_policy, codex_runner, git_utils, reviewer, verifier
from app.config import Settings
from app.database import Store, now
from app.execution_events import parse
from app.locks import lease
from app.repository import fingerprint
from app.security import redact, sanitize

STAGES = ["The Meeting", "The Plan", "The Hitman", "The Cleanup", "The Inspection", "The Verdict"]


class Workflow:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.active: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}

    async def start(
        self,
        request: str,
        prompt: str,
        workspace: Path,
        plan_id: str | None = None,
        revision: int | None = None,
        max_repairs: int = 0,
    ) -> str:
        if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
            raise ValueError("Repair allowance must be between zero and two")
        # This runs on one event loop; the partial unique DB index also enforces the lock.
        if any(self.store.get(task_id)["workspace"] == str(workspace) for task_id in self.active):
            raise ValueError("A contract is already running in this workspace.")
        await git_utils.require_clean(workspace)
        if len(self.active) >= self.settings.max_active_tasks:
            raise ValueError("Local execution capacity reached. Retry when a contract finishes.")
        try:
            task_id = self.store.create(
                redact(request, self.settings.api_key),
                redact(prompt, self.settings.api_key),
                str(workspace),
                plan_id=plan_id,
                revision=revision,
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A contract is already running in this workspace.") from exc
        cancel = asyncio.Event()
        task = asyncio.create_task(self.run(task_id, workspace, prompt, cancel, max_repairs))
        self.active[task_id] = (task, cancel)
        return task_id

    def event(self, task_id: str, kind: str, text: str):
        self.store.event(task_id, kind, redact(text, self.settings.api_key))

    def codex_event(self, task_id: str, text: str):
        metadata = parse(text)
        if metadata:
            self.store.metadata(task_id, **sanitize(metadata, self.settings.api_key))
        self.event(task_id, "codex", text)

    def stage(self, task_id: str, number: int):
        self.store.update(task_id, stage=number)
        self.event(task_id, "stage", STAGES[number])

    async def run(
        self,
        task_id: str,
        workspace: Path,
        prompt: str,
        cancel: asyncio.Event,
        max_repairs: int = 0,
    ):
        status, message = "BLOCKED", "Execution did not complete."
        evidence = []
        workspace_lease = None
        try:
            self.store.transition(task_id, "ANALYZING")
            self.stage(task_id, 0)
            # Revalidate immediately before subprocess execution.
            if self.settings.workspace(str(workspace)) != workspace:
                raise ValueError("Workspace changed since approval.")
            workspace_lease = lease(workspace / ".git" / "don-codino.writer.lock")
            workspace_lease.__enter__()
            await git_utils.require_clean(workspace)
            self.stage(task_id, 1)
            self.event(task_id, "info", "The edited plan was approved for this workspace.")
            ready = await codex_runner.availability(self.settings)
            if cancel.is_set():
                raise asyncio.CancelledError
            if not ready["available"]:
                message = "Our associate Codex is unavailable. " + ready["message"]
                return
            # Older API contracts keep their existing adapter behavior. V2 requires a
            # live capability probe before any coding subprocess is launched.
            if self.store.execution(task_id)["plan_id"]:
                supported = await codex_runner.capabilities(self.settings)
                if not supported["available"]:
                    message = supported["message"]
                    return
            self.stage(task_id, 2)
            for attempt in range(max_repairs + 1):
                if cancel.is_set():
                    raise asyncio.CancelledError
                self.store.transition(task_id, "EXECUTING")
                protected = check_policy.protected_files(workspace) if attempt else None
                self.store.metadata(task_id, attempts=attempt)
                binary = codex_runner.executable(self.settings)
                invocation = {
                    "command": codex_runner.command(
                        binary or self.settings.codex_binary, workspace
                    ),
                    "cwd": str(workspace),
                    "mode": "exec",
                    "started_at": now(),
                    "attempt": attempt,
                    "prompt_transport": "stdin",
                    "authorized_max_repairs": max_repairs,
                }
                self.store.metadata(task_id, invocation=invocation)
                self.event(task_id, "invocation", str(invocation))
                result = await codex_runner.execute(
                    self.settings,
                    workspace,
                    prompt,
                    cancel,
                    lambda text: self.codex_event(task_id, text),
                )
                self.store.update(task_id, exit_code=result.code)
                evidence.append(
                    {
                        "kind": "codex",
                        **invocation,
                        "ended_at": now(),
                        "exit_code": result.code,
                        "session_id": self.store.execution(task_id)["session_id"],
                        "usage": self.store.execution(task_id)["usage"],
                    }
                )
                self.store.metadata(task_id, evidence=evidence)
                if cancel.is_set():
                    raise asyncio.CancelledError
                if result.code:
                    status, message = "FAIL", f"Codex exited with status {result.code}."
                    return
                if protected is not None and check_policy.protected_files(workspace) != protected:
                    message = (
                        "Repair changed tests or check configuration. Human inspection required."
                    )
                    self.event(task_id, "policy", message)
                    return
                self.store.transition(task_id, "TESTING")
                self.stage(task_id, 3)
                started = now()
                report = await verifier.verify(
                    self.settings,
                    workspace,
                    cancel,
                    lambda text: self.event(task_id, "verification", text),
                )
                if cancel.is_set():
                    raise asyncio.CancelledError
                report = sanitize(report, self.settings.api_key)
                evidence.append(
                    {
                        "kind": "verification",
                        "attempt": attempt,
                        "started_at": started,
                        "ended_at": now(),
                        "report": report,
                    }
                )
                self.store.metadata(task_id, evidence=evidence)
                self.store.update(task_id, verification=report)
                if report["status"] != "FAIL" or attempt >= max_repairs:
                    break
                self.store.transition(task_id, "REPAIRING", "Previously approved bounded repair")
                self.event(task_id, "repair", f"Focused repair {attempt + 1}/{max_repairs}")
                prompt = (
                    "Original approved scope (do not expand):\n"
                    f"{self.store.get(task_id)['prompt']}\n"
                    "Repair only the implementation causing these check failures. Do not delete or "
                    "weaken tests, assertions, security controls, or check configuration. Do not "
                    "install dependencies or execute tests on the host. "
                    "If scope must expand, stop.\n"
                    f"Untrusted verification diagnostics:\n{str(report)[:16000]}"
                )
            status = report["status"]
            message = {
                "PASS": "Business is concluded, Boss.",
                "FAIL": "Someone left fingerprints in the code.",
                "BLOCKED": "Verification is blocked. Review the evidence.",
            }[status]
            if status == "PASS" and self.store.execution(task_id)["plan_id"]:
                self.store.transition(task_id, "REVIEWING")
                review = await reviewer.review(
                    self.settings,
                    workspace,
                    self.store.get(task_id)["request"]
                    + "\nApproved final plan:\n"
                    + self.store.get(task_id)["prompt"],
                    report,
                    cancel,
                    lambda text: self.event(task_id, "review", text),
                )
                evidence.append({"kind": "review", "report": review})
                self.store.metadata(task_id, evidence=evidence)
                self.store.transition(task_id, "SECURITY_CHECKING")
                files, diff = await git_utils.inspect(workspace)
                security = check_policy.security_report(diff, files)
                evidence.append({"kind": "security", "report": security})
                self.store.metadata(task_id, evidence=evidence)
                if review["status"] != "PASS" or security["status"] != "PASS":
                    status, message = "BLOCKED", "Review or security findings block readiness."
                else:
                    message = (
                        "Checks passed. Independent model review recorded. Human review required."
                    )
        except asyncio.CancelledError:
            status, message = "CANCELLED", "Contract cancelled. Partial changes may remain."
        except (OSError, ValueError, TimeoutError) as exc:
            status = "BLOCKED"
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
            if cancel.is_set():
                status, message = "CANCELLED", "Contract cancelled. Partial changes may remain."
            target = {"PASS": "VERIFIED", "FAIL": "FAILED", "CANCELLED": "CANCELLED"}.get(
                status, "BLOCKED"
            )
            self.store.transition(task_id, target, message)
            self.event(task_id, "verdict", message)
            self.store.update(
                task_id,
                status=status,
                message=redact(message, self.settings.api_key),
                ended_at=now(),
            )
            if status == "PASS":
                try:
                    self.store.remember(task_id, fingerprint(workspace))
                except (OSError, ValueError):
                    self.event(task_id, "memory", "Outcome could not be added to verified memory.")
            self.active.pop(task_id, None)
            if workspace_lease:
                workspace_lease.__exit__(None, None, None)

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
