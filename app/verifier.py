"""Run untrusted project tests only inside an offline, restricted Docker container."""

import asyncio
import io
import json
import re
import shutil
import tarfile
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.git_utils import git
from app.process import run


async def availability(settings: Settings) -> dict:
    if not shutil.which("docker"):
        return {"available": False, "message": "Docker is not installed; verification is BLOCKED."}
    try:
        daemon = await run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
        # Some Docker CLI versions exit 0 for formatted info even on a connection error.
        has_server_version = any(
            re.fullmatch(r"\d+\.\d+\.\d+[^\s]*", line.strip())
            for line in daemon.output.splitlines()
        )
        if daemon.code or not has_server_version:
            return {"available": False, "message": "Docker daemon is unavailable."}
        image = await run(["docker", "image", "inspect", settings.verifier_image], timeout=10)
        return {
            "available": image.code == 0,
            "message": "Offline verification ready."
            if image.code == 0
            else "Build the verifier image: docker build -t don-codino-verifier:local verification",
        }
    except (OSError, TimeoutError) as exc:
        return {"available": False, "message": str(exc)}


async def snapshot(workspace: Path) -> bytes:
    result = await git(workspace, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if result.code:
        raise ValueError("Could not enumerate workspace files for verification.")
    archive = io.BytesIO()
    total = 0
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name in sorted(set(result.output.split("\0")) - {""}):
            relative = Path(name)
            # Never copy Git metadata, credentials, links, devices, or host paths.
            if any(part.startswith(".") for part in relative.parts):
                continue
            path = workspace / relative
            if (
                path.is_symlink()
                or not path.resolve().is_relative_to(workspace)
                or not path.is_file()
            ):
                continue
            size = path.stat().st_size
            total += size
            if total > 20_000_000:
                raise ValueError("Verification snapshot exceeds 20 MB; narrow the project.")
            contents = path.read_bytes()
            info = tarfile.TarInfo(relative.as_posix())
            info.size = len(contents)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(contents))
    return archive.getvalue()


async def verify(settings: Settings, workspace: Path, cancel: asyncio.Event, emit) -> dict:
    ready = await availability(settings)
    if not ready["available"]:
        return {"status": "BLOCKED", "message": ready["message"]}
    name = "don-codino-" + uuid4().hex
    try:
        data = await snapshot(workspace)
        result = await run(
            [
                "docker",
                "run",
                "--rm",
                "--interactive",
                "--pull=never",
                "--name",
                name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--memory=512m",
                "--cpus=1",
                "--user=65534:65534",
                "--tmpfs=/workspace:rw,nosuid,nodev,size=128m,mode=1777",
                "--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777",
                settings.verifier_image,
            ],
            data=data,
            timeout=min(settings.timeout_seconds, 300),
            cancel=cancel,
        )
        emit(result.output)
        try:
            # The trusted entrypoint prints one JSON line. Docker itself may write
            # configuration warnings before it on the merged stdout/stderr pipe.
            diagnostics, _, report_line = (result.stdout or result.output).strip().rpartition("\n")
            report = json.loads(report_line)
        except json.JSONDecodeError:
            return {"status": "BLOCKED", "message": result.output or "No verifier report returned."}
        if (
            result.code
            or not isinstance(report, dict)
            or not all(
                isinstance(report.get(key), dict)
                and isinstance(report[key].get("exit_code"), int)
                and isinstance(report[key].get("output"), str)
                for key in ("tests", "lint")
            )
        ):
            return {"status": "BLOCKED", "message": "Verifier failed to produce a valid report."}
        tests, lint = report["tests"], report["lint"]
        status = "PASS" if tests["exit_code"] == 0 and lint["exit_code"] == 0 else "FAIL"
        if tests["exit_code"] == 5:
            status = "BLOCKED"
        return {**report, "status": status, "diagnostics": diagnostics}
    except (OSError, ValueError, TimeoutError) as exc:
        return {"status": "BLOCKED", "message": str(exc)}
    finally:
        # Remove a container even when docker run was cancelled or timed out.
        try:
            await run(["docker", "rm", "--force", name], timeout=15)
        except (OSError, TimeoutError):
            emit(f"Container cleanup could not be confirmed. Inspect Docker container {name}.")
