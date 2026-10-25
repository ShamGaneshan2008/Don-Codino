"""Trusted container entrypoint, outside the untrusted project import path."""

import io
import json
import re
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

root = Path("/workspace")
data = sys.stdin.buffer.read(25_000_001)
if len(data) > 25_000_000:
    raise ValueError("Snapshot too large")
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    for member in archive:
        target = (root / member.name).resolve()
        if not member.isfile() or not target.is_relative_to(root):
            raise ValueError("Unsafe archive entry")
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        target.write_bytes(source.read())


def check(command):
    # Spool to disk so a noisy test cannot exhaust the runner's Python heap.
    log = Path("/tmp") / ("pytest.log" if "pytest" in command else "ruff.log")  # noqa: S108
    error_log = log.with_suffix(".stderr")
    started = datetime.now(UTC).isoformat()
    try:
        with log.open("wb") as output, error_log.open("wb") as errors:
            completed = subprocess.run(  # noqa: S603
                command,
                cwd=root,
                stdout=output,
                stderr=errors,
                timeout=120,
                check=False,
            )
        with log.open("rb") as output:
            stdout = output.read(16000).decode("utf-8", errors="replace")
        with error_log.open("rb") as errors:
            stderr = errors.read(8000).decode("utf-8", errors="replace")
        text = stdout + stderr
        counts = {
            name: int(match.group(1))
            for name in ("passed", "failed", "skipped")
            if (match := re.search(r"(\d+) " + name, text))
        }
        return {
            "exit_code": completed.returncode,
            "output": text,
            "stdout": stdout,
            "stderr": stderr,
            "command": command,
            "cwd": str(root),
            "environment": "offline unprivileged Linux container",
            "started_at": started,
            "ended_at": datetime.now(UTC).isoformat(),
            "counts_from_summary": counts,
            "truncated": log.stat().st_size > 16000 or error_log.stat().st_size > 8000,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 124,
            "output": "Verification exceeded 120 seconds.",
            "command": command,
            "cwd": str(root),
            "started_at": started,
            "ended_at": datetime.now(UTC).isoformat(),
        }


print(
    json.dumps(
        {
            "tests": check([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
            "lint": check(["/usr/local/bin/ruff", "check", "--no-cache", "."]),
        }
    )
)
