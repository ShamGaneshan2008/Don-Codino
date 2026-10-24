"""Read-only Git inspection; tasks start from a clean working tree."""

from pathlib import Path

from app.process import run


async def git(workspace: Path, *args: str):
    return await run(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.pager=cat",
            "-C",
            str(workspace),
            *args,
        ]
    )


async def require_clean(workspace: Path):
    root = await git(workspace, "rev-parse", "--show-toplevel")
    if root.code or Path(root.output.strip()).resolve() != workspace:
        raise ValueError("Git working tree must match the approved workspace.")
    result = await git(workspace, "status", "--porcelain", "--untracked-files=all")
    if result.code or result.output.strip():
        raise ValueError("Workspace must be a clean Git repository. Commit or stash changes first.")


async def inspect(workspace: Path) -> tuple[list[str], str]:
    result = await git(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    if result.code:
        raise ValueError("Git inspection failed: " + result.output)
    files = [line[3:] for line in result.output.splitlines() if len(line) > 3]
    head = await git(workspace, "rev-parse", "--verify", "HEAD")
    base = ["HEAD"] if head.code == 0 else []
    diff = await git(workspace, "diff", *base, "--no-ext-diff", "--no-textconv", "--", ".")
    if diff.code:
        raise ValueError("Git diff failed: " + diff.output)
    text = diff.output
    if not base:
        staged = await git(workspace, "diff", "--cached", "--no-ext-diff", "--no-textconv")
        if staged.code:
            raise ValueError("Staged Git diff failed: " + staged.output)
        text += staged.output
    untracked = await git(workspace, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked.code:
        raise ValueError("Untracked file inspection failed: " + untracked.output)
    for name in untracked.output.split("\0"):
        if not name:
            continue
        path = workspace / name
        if path.is_symlink() or not path.resolve().is_relative_to(workspace):
            text += f"\nUntracked link omitted: {name}\n"
        elif path.is_file() and path.stat().st_size < 64_000:
            text += f"\n--- /dev/null\n+++ b/{name}\n"
            text += "".join(
                "+" + line + "\n"
                for line in path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()
            )
        else:
            text += f"\nUntracked file omitted (large or special): {name}\n"
        if len(text) > 256_000:
            break
    return files, text[:256_000]
