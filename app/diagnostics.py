"""Read-only integration diagnostics. Never returns credential material."""

import asyncio
import importlib.metadata
import platform
import shutil

from app import codex_runner, verifier
from app.database import Store
from app.process import run
from app.security import sanitize


async def github_status():
    if not shutil.which("gh"):
        return {
            "available": False,
            "authenticated": False,
            "message": "Optional gh CLI not installed",
        }
    try:
        result = await run(["gh", "auth", "status", "--hostname", "github.com"], timeout=10)
        return {
            "available": True,
            "authenticated": result.code == 0,
            "message": "GitHub authenticated" if result.code == 0 else "GitHub login required",
        }
    except (OSError, TimeoutError):
        return {"available": False, "authenticated": False, "message": "GitHub CLI check failed"}


async def report(settings):
    codex, capabilities, isolation, github = await asyncio.gather(
        codex_runner.availability(settings),
        codex_runner.capabilities(settings),
        verifier.availability(settings),
        github_status(),
    )
    dependencies = {}
    for package in ("fastapi", "uvicorn", "pydantic", "httpx", "python-dotenv"):
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = "MISSING"
    store = Store(settings.database)
    with store.connection() as db:
        database = {
            "check": db.execute("PRAGMA quick_check").fetchone()[0],
            "schema_version": db.execute("SELECT max(version) FROM schema_migrations").fetchone()[
                0
            ],
        }
    git = {"available": bool(shutil.which("git"))}
    if git["available"]:
        try:
            result = await run(["git", "--version"], timeout=5)
            git = {"available": result.code == 0, "version": result.output.strip()}
        except (OSError, TimeoutError):
            git = {"available": False}
    return sanitize(
        {
            "python": platform.python_version(),
            "dependencies": dependencies,
            "database": database,
            "codex": codex,
            "capabilities": capabilities,
            "git": git,
            "github": github,
            "verification": isolation,
            "workspace_root": str(settings.workspace_root),
            "workspaces": settings.discover_workspaces(),
            "startup": "uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765",
        },
        settings.api_key,
    )
