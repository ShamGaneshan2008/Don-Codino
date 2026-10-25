"""Opt-in real calculator contract. No remote writes; tests run only in the verifier."""

import argparse
import ast
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import verifier  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Authorize a real coding run")
    parser.add_argument("--root", type=Path, required=True, help="Disposable workspace parent")
    parser.add_argument("--image", default="don-codino-verifier:v2-validation")
    parser.add_argument(
        "--controlled-failure",
        action="store_true",
        help="Inject one arithmetic defect before real isolated verification",
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("Real Codex execution requires --execute")
    root = args.root.resolve()
    workspace = root / ("calculator-" + uuid4().hex[:10])
    workspace.mkdir(parents=True)
    subprocess.run(  # noqa: S603 -- fixed Git init in the explicitly selected disposable root
        [shutil.which("git"), "-C", str(workspace), "init"],
        check=True,
        capture_output=True,
    )
    settings = Settings(
        workspace_root=root,
        database=root / (workspace.name + ".sqlite3"),
        verifier_image=args.image,
        timeout_seconds=300,
    )
    application = create_app(settings)
    original_verify = verifier.verify
    injected = False

    async def inject_then_verify(configuration, path, cancel, emit):
        nonlocal injected
        if not injected:
            source = path / "calculator.py"
            tree = ast.parse(source.read_text(encoding="utf-8"))
            modified = False
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "add":
                    for child in ast.walk(node):
                        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Add):
                            child.op = ast.Sub()
                            modified = True
            if not modified:
                raise ValueError("Acceptance fault injection could not locate add's sum")
            source.write_text(ast.unparse(tree) + "\n", encoding="utf-8")
            injected = True
            emit(
                "ACCEPTANCE FIXTURE: changed add from addition to subtraction before actual checks"
            )
        return await original_verify(configuration, path, cancel, emit)

    if args.controlled_failure:
        verifier.verify = inject_then_verify
    with TestClient(application, base_url="http://127.0.0.1") as client:
        request = (
            "Create a Python calculator with add, subtract, multiply and divide functions, "
            "division-by-zero handling, and a command-line interface using argparse. "
            "Include pytest coverage for positive/negative numbers, division by zero, "
            "invalid numeric CLI inputs and CLI results. Use only the standard library and pytest. "
            "Do not run tests or project scripts on the host."
        )
        result = client.post(
            "/api/v1/plans", json={"workspace": str(workspace), "request": request}
        )
        result.raise_for_status()
        plan = result.json()
        print(json.dumps({"plan_id": plan["plan_id"], "workspace": str(workspace)}), flush=True)
        endpoint = f"/api/v1/plans/{plan['plan_id']}"
        approved = {"approved": True, "revision": plan["revision"]}
        client.post(endpoint + "/approve", json=approved).raise_for_status()
        started = client.post(endpoint + "/execute", json={**approved, "max_repairs": 1})
        started.raise_for_status()
        task_id = started.json()["id"]
        print(json.dumps({"task_id": task_id, "status": "started"}), flush=True)

        async def settle():
            task = application.state.workflow.active.get(task_id)
            if task:
                await asyncio.wait_for(asyncio.shield(task[0]), timeout=1000)

        client.portal.call(settle)
        record = client.get(f"/api/tasks/{task_id}").json()
        record["acceptance_fixture"] = {
            "controlled_failure_requested": args.controlled_failure,
            "fault_injected": injected,
        }
        evidence = root / (workspace.name + "-evidence.json")
        evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": record["status"],
                    "exit_code": record["exit_code"],
                    "verification": record["verification"],
                    "evidence": str(evidence),
                    "files": record["changed_files"],
                },
                indent=2,
            ),
            flush=True,
        )
        return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
