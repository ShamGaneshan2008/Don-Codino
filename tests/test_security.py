import asyncio
import io
import tarfile
from dataclasses import replace

import pytest

from app.config import SOURCE_ROOT
from app.database import Store
from app.security import redact, sanitize
from app.verifier import snapshot


def test_workspace_rejects_escape_source_and_uninitialized(settings, tmp_path):
    with pytest.raises(ValueError):
        settings.workspace(str(tmp_path))
    with pytest.raises(ValueError):
        replace(settings, workspace_root=SOURCE_ROOT).workspace(str(SOURCE_ROOT))
    (settings.workspace_root / "not-git").mkdir()
    with pytest.raises(ValueError):
        settings.workspace("not-git")


def test_workspace_rejects_symlink_escape(settings, tmp_path):
    link = settings.workspace_root / "escape"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows Developer Mode or privileges")
    with pytest.raises(ValueError):
        settings.workspace("escape")
    assert "escape" not in {item["name"] for item in settings.discover_workspaces()}


def test_workspace_rejects_external_git_metadata(settings, tmp_path):
    project = settings.workspace_root / "linked-git"
    project.mkdir()
    try:
        (project / ".git").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows Developer Mode or privileges")
    with pytest.raises(ValueError):
        settings.workspace("linked-git")
    assert "linked-git" not in {item["name"] for item in settings.discover_workspaces()}


def test_secrets_are_redacted():
    text = redact(
        "sk-abcdefghijk token=abc password=hunter2 Bearer xyz explicit-key", "explicit-key"
    )
    for secret in ("sk-abcdefghijk", "abc", "hunter2", "xyz", "explicit-key"):
        assert secret not in text
    assert "[REDACTED]" in text


def test_snapshot_omits_secrets_and_git_metadata(workspace):
    (workspace / ".env").write_text("token=secret", encoding="utf-8")
    (workspace / "calc.py").write_text("x = 1\n", encoding="utf-8")
    data = asyncio.run(snapshot(workspace))
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        assert archive.getnames() == ["README.md", "calc.py"]


def test_structured_redaction_preserves_report_shape():
    report = {"tests": {"exit_code": 0, "output": "token=abcdef"}, "status": "PASS"}
    clean = sanitize(report)
    assert clean["tests"]["output"] == "token=[REDACTED]"
    assert clean["tests"]["exit_code"] == 0
    assert clean["status"] == "PASS"


def test_json_log_credentials_are_redacted():
    import json

    log = '{"password": "a phrase with spaces", "api_key":"plain-credential", "ok":true}'
    clean = json.loads(redact(log))
    assert clean["password"] == "[REDACTED]"  # noqa: S105 -- expected redaction marker
    assert clean["api_key"] == "[REDACTED]"
    assert clean["ok"] is True


def test_sensitive_fields_are_redacted_in_structured_data():
    report = {"output": {"token": "opaque-credential", "count": 3}}
    assert sanitize(report) == {"output": {"token": "[REDACTED]", "count": 3}}


def test_database_lock_and_restart_recovery(settings):
    import sqlite3

    store = Store(settings.database)
    task_id = store.create("request", "prompt", "workspace")
    with pytest.raises(sqlite3.IntegrityError):
        store.create("request", "prompt", "workspace")
    store.recover()
    assert store.get(task_id)["status"] == "BLOCKED"
    assert store.get(task_id)["ended_at"]
    assert store.create("request", "prompt", "workspace") != task_id
