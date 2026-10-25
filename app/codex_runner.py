"""Real Codex CLI adapter. Escalations are denied, never auto-approved."""

import asyncio
import os
import platform
import shutil
from pathlib import Path

from app.config import Settings
from app.process import run
from app.prompt_engine import CONSTRAINTS


async def capabilities(settings: Settings) -> dict:
    binary = executable(settings)
    if not binary:
        return {"available": False, "message": "Native Codex executable unavailable"}
    try:
        result = await run([binary, "exec", "--help"], timeout=10)
        required = ["--json", "--sandbox", "--cd", "--ignore-user-config", "--ignore-rules"]
        missing = [flag for flag in required if flag not in result.output]
        return {
            "available": result.code == 0 and not missing,
            "binary": binary,
            "missing_flags": missing,
            "structured_output": "--output-schema" in result.output,
            "resume_supported": "resume" in result.output,
            "message": "Supported exec interface detected"
            if not missing and result.code == 0
            else "Installed Codex does not expose the required restricted exec interface",
        }
    except (OSError, TimeoutError) as exc:
        return {"available": False, "message": str(exc)}


def executable(settings: Settings) -> str | None:
    path = shutil.which(settings.codex_binary)
    if not path:
        return None
    launcher = Path(path)
    if launcher.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return path
    # Never execute a shell wrapper. Resolve only known npm Codex package layouts.
    if os.name != "nt" or launcher.stem.lower() != "codex":
        return None
    architecture = platform.machine().lower()
    target = {
        "amd64": ("x64", "x86_64"),
        "x86_64": ("x64", "x86_64"),
        "arm64": ("arm64", "aarch64"),
        "aarch64": ("arm64", "aarch64"),
    }.get(architecture)
    if target is None:
        return None
    package_arch, triple_arch = target
    scope = launcher.parent / "node_modules" / "@openai"
    package = scope / "codex"
    platform_package = f"codex-win32-{package_arch}"
    roots = [
        package / "node_modules" / "@openai" / platform_package,
        scope / platform_package,
        package,
    ]
    for root in roots:
        for directory in ("bin", "codex"):
            candidate = root / "vendor" / f"{triple_arch}-pc-windows-msvc" / directory / "codex.exe"
            if candidate.is_file():
                return str(candidate.resolve())
    return None


async def availability(settings: Settings) -> dict:
    binary = executable(settings)
    if not binary:
        return {
            "available": False,
            "message": "Our associate Codex is unavailable. "
            f"Could not resolve {settings.codex_binary!r} to a native executable. "
            "Install the CLI including its platform package, or set DON_CODEX_BINARY "
            "to the full path of codex.exe. Shell wrappers are never executed.",
        }
    try:
        version = await run([binary, "--version"], timeout=10)
        if version.code:
            return {
                "available": False,
                "message": f"Codex --version exited {version.code}: {version.output.strip()}",
            }
        auth = await run([binary, "login", "status"], timeout=10)
    except (OSError, TimeoutError) as exc:
        return {"available": False, "message": f"Could not run {binary}: {exc}"}
    return {
        "available": version.code == 0 and auth.code == 0,
        "version": version.output.strip(),
        "message": auth.output.strip()
        if auth.code == 0
        else (
            f"Codex login status exited {auth.code}: {auth.output.strip()}. "
            "Run codex login in your own terminal."
        ),
    }


def command(binary: str, workspace: Path) -> list[str]:
    # User config is ignored, so explicitly retain the Windows OS sandbox.
    # "elevated" names the restricted sandbox implementation, not unrestricted execution.
    windows_sandbox = ["-c", 'windows.sandbox="elevated"'] if os.name == "nt" else []
    return [
        binary,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "workspace-write",
        "--json",
        "--color",
        "never",
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        'shell_environment_policy.inherit="core"',
        *windows_sandbox,
        "--cd",
        str(workspace),
        "-",
    ]


def environment():
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "CODEX_HOME",
        }
    }


async def execute(settings: Settings, workspace: Path, prompt: str, cancel: asyncio.Event, emit):
    binary = executable(settings)
    if not binary:
        raise ValueError("Our associate Codex is unavailable.")
    return await run(
        command(binary, workspace),
        cwd=workspace,
        timeout=settings.timeout_seconds,
        cancel=cancel,
        emit=emit,
        data=f"{CONSTRAINTS}\n\nApproved task\n{prompt}".encode(),
        env=environment(),
    )
