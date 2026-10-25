"""Non-executing security checks and repair guards; never claims a dependency audit."""

import hashlib
import re
from pathlib import Path

from app.repository import inspect, linked
from app.security import redact


def protected_files(workspace):
    result = {}
    for name in inspect(workspace)["files"]:
        path = workspace / name
        if "test" in name.lower() or Path(name).name in {
            "pyproject.toml",
            "package.json",
            "pytest.ini",
            "setup.cfg",
            "tox.ini",
            "package-lock.json",
            "requirements.txt",
        }:
            if not linked(path) and path.resolve().is_relative_to(workspace):
                if path.stat().st_size > 2_000_000:
                    raise ValueError("Protected test/configuration file exceeds the repair limit")
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in (".gitignore", ".ruff.toml", ".coveragerc"):
        path = workspace / name
        if path.is_file() and not linked(path) and path.stat().st_size <= 64000:
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def security_report(diff, files):
    findings = []
    additions = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if redact(additions) != additions:
        findings.append(
            {
                "severity": "high",
                "category": "possible-secret",
                "evidence": "Added text matches a credential pattern; value withheld.",
            }
        )
    if re.search(r"dangerously-bypass-approvals|sandbox.*danger-full-access", additions):
        findings.append(
            {
                "severity": "high",
                "category": "sandbox-bypass",
                "evidence": "Added text contains unrestricted execution flags.",
            }
        )
    return {
        "status": "BLOCKED" if findings else "PASS",
        "findings": findings,
        "method": "bounded static diff patterns; not a comprehensive security audit",
        "files_examined": files,
        "dependency_audit": {
            "status": "NOT RUN",
            "message": "No isolated dependency auditor configured",
        },
    }
