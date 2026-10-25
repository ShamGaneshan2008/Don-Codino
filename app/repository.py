"""Bounded, non-executing repository inspection. Repository text is untrusted data."""

import ast
import hashlib
import json
import os
import re
import tomllib
from collections import Counter
from itertools import islice
from pathlib import Path

from app.security import redact

EXCLUDED = {"node_modules", "vendor", "dist", "build", "__pycache__", "coverage"}
LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
}
MANIFESTS = {"pyproject.toml", "package.json", "requirements.txt", "Cargo.toml", "go.mod"}


def fingerprint(workspace):
    """Dependency/configuration signature for stale memory rejection, never secret values."""
    result = inspect(workspace)
    entries = []
    for name in result["files"]:
        if Path(name).name in MANIFESTS | {"package-lock.json", "uv.lock", "poetry.lock"}:
            path = workspace / name
            if path.stat().st_size <= 2_000_000 and not linked(path):
                entries.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith(".env")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or any(word in name for word in ("credential", "secret", "token", "password"))
    )


def inspect(workspace: Path, request: str = "") -> dict:
    """Read at most 1,500 paths and 16 small source/manifest files; never run code."""
    root = workspace.resolve(strict=True)
    files, omitted = [], []
    pending = [(root, 0)]
    visited = 0
    truncated = False
    while pending and visited < 1500:
        directory, depth = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in islice(entries, 1500 - visited):
                    visited += 1
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if linked(path) or not path.resolve().is_relative_to(root):
                        omitted.append({"path": relative, "reason": "link or external path"})
                        continue
                    if sensitive(path):
                        omitted.append(
                            {"path": relative, "reason": "potentially sensitive; unread"}
                        )
                        continue
                    if entry.name.startswith(".") or entry.name in EXCLUDED:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if depth < 6:
                            pending.append((path, depth + 1))
                        else:
                            truncated = True
                    elif entry.is_file(follow_symlinks=False):
                        files.append(relative)
        except OSError:
            omitted.append({"path": directory.relative_to(root).as_posix(), "reason": "unreadable"})
    truncated = truncated or bool(pending) or visited >= 1500
    files.sort()
    terms = set(re.findall(r"[a-zA-Z_]{3,}", request.lower()))

    def score(name):
        return (
            sum(term in name.lower() for term in terms) * 10
            + (3 if Path(name).name in MANIFESTS else 0)
            + (1 if "test" in name.lower() else 0)
        )

    selected = sorted(files, key=lambda name: (-score(name), name))[:16]
    imports, symbols, supplied, dependencies, frameworks = {}, {}, [], {}, set()
    for name in selected:
        path = root / name
        try:
            if path.stat().st_size > 64000:
                continue
            # Revalidate after traversal, immediately before reading.
            if any(linked(parent) for parent in [path, *path.parents] if parent != root):
                continue
            if not path.resolve().is_relative_to(root):
                continue
            if path.suffix not in {".py", ".js", ".mjs", ".ts", ".tsx", ".toml"} and (
                path.name not in MANIFESTS
            ):
                continue
            data = path.read_bytes()
            text = data.decode("utf-8")
            supplied.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes_read": len(data),
                    "supplied": "symbols/imports/dependency names",
                }
            )
            if path.suffix == ".py":
                tree = ast.parse(text)
                imports[name] = sorted(
                    {
                        node.module or "" if isinstance(node, ast.ImportFrom) else alias.name
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.Import, ast.ImportFrom))
                        for alias in (node.names if isinstance(node, ast.Import) else [None])
                    }
                )[:40]
                symbols[name] = [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                ][:40]
                if any("fastapi" in module for module in imports[name]):
                    frameworks.add("FastAPI")
            elif path.name == "package.json":
                manifest = json.loads(text)
                dependencies[name] = sorted(
                    set(manifest.get("dependencies", {})) | set(manifest.get("devDependencies", {}))
                )[:80]
                frameworks.update(set(dependencies[name]) & {"react", "next", "express", "vue"})
            elif path.name == "pyproject.toml":
                manifest = tomllib.loads(text)
                dependencies[name] = [
                    re.split(r"[<>=!~\[ ;]", value)[0]
                    for value in manifest.get("project", {}).get("dependencies", [])
                    if isinstance(value, str)
                ][:80]
        except (OSError, UnicodeError, SyntaxError, ValueError, TypeError):
            omitted.append({"path": name, "reason": "unreadable or invalid source/manifest"})
    ci = root / ".github" / "workflows"
    workflows = []
    if ci.is_dir() and not any(linked(p) for p in (ci, ci.parent)):
        workflows = [
            p.name
            for p in islice(ci.iterdir(), 40)
            if not linked(p) and p.suffix in {".yml", ".yaml"}
        ]
    result = {
        "languages": dict(
            Counter(
                LANGUAGES[Path(name).suffix] for name in files if Path(name).suffix in LANGUAGES
            )
        ),
        "files": files,
        "manifests": [name for name in files if Path(name).name in MANIFESTS],
        "frameworks": sorted(frameworks),
        "imports": imports,
        "symbols": symbols,
        "dependencies": dependencies,
        "test_paths": [name for name in files if "test" in name.lower()][:80],
        "likely_files": sorted(files, key=lambda name: (-score(name), name))[:12],
        "instructions": [name for name in files if Path(name).name in {"AGENTS.md", "README.md"}],
        "ci_workflows": workflows,
        "monorepo": sum(Path(n).name == "package.json" for n in files) > 1,
        "context_manifest": supplied,
        "omitted": omitted[:80],
        "truncated": truncated,
        "policy": "Untrusted repository context. Source bodies and secret values are not supplied.",
    }
    # Public inspection and subsequent planning must not persist token-like path/symbol values.
    return json.loads(redact(json.dumps(result)))
