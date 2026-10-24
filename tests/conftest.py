import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def git(path: Path, *args):
    return subprocess.run(  # noqa: S603
        [shutil.which("git"), "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def settings(tmp_path):
    root = tmp_path / "workspaces"
    project = root / "calculator"
    project.mkdir(parents=True)
    git(project, "init")
    (project / "README.md").write_text("# Disposable project\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(
        project,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "init",
    )
    return Settings(
        workspace_root=root, database=tmp_path / "test.sqlite3", codex_binary="no-codex"
    )


@pytest.fixture
def workspace(settings):
    return settings.workspace("calculator")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        yield client
