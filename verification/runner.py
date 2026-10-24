"""Trusted container entrypoint, outside the untrusted project import path."""

import io
import json
import subprocess
import sys
import tarfile
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
    try:
        with log.open("wb") as output:
            completed = subprocess.run(  # noqa: S603
                command,
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        with log.open("rb") as output:
            text = output.read(80_000).decode("utf-8", errors="replace")
        return {"exit_code": completed.returncode, "output": text}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "output": "Verification exceeded 120 seconds."}


print(
    json.dumps(
        {
            "tests": check([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
            "lint": check(["/usr/local/bin/ruff", "check", "--no-cache", "."]),
        }
    )
)
