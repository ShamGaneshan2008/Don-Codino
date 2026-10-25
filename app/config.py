"""Configuration and the workspace trust boundary."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SOURCE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    database: Path
    codex_binary: str = "codex"
    timeout_seconds: int = 600
    verifier_image: str = "don-codino-verifier:local"
    api_key: str = ""
    model: str = ""
    max_active_tasks: int = 2

    @classmethod
    def from_env(cls):
        load_dotenv(SOURCE_ROOT / ".env")
        return cls(
            workspace_root=Path(
                os.getenv("DON_WORKSPACE_ROOT", SOURCE_ROOT / "workspaces")
            ).resolve(),
            database=Path(
                os.getenv("DON_DATABASE", SOURCE_ROOT / "data/don-codino.sqlite3")
            ).resolve(),
            codex_binary=os.getenv("DON_CODEX_BINARY", "codex"),
            timeout_seconds=max(10, min(3600, int(os.getenv("DON_TIMEOUT_SECONDS", "600")))),
            verifier_image=os.getenv("DON_VERIFIER_IMAGE", "don-codino-verifier:local"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("DON_OPENAI_MODEL", ""),
            max_active_tasks=max(1, min(4, int(os.getenv("DON_MAX_ACTIVE_TASKS", "2")))),
        )

    def workspace(self, value: str) -> Path:
        root = self.workspace_root.resolve()
        candidate = Path(value)
        path = (root / candidate).resolve(strict=True)
        if not path.is_dir() or not path.is_relative_to(root):
            raise ValueError("Choose a directory inside the configured workspace root.")
        if path.parent != root:
            raise ValueError("Choose a direct child of the configured workspace root.")
        # A separately initialized sample repository inside workspaces is safe.
        if path == SOURCE_ROOT or SOURCE_ROOT.is_relative_to(path):
            raise ValueError("The Don Codino source repository cannot be a task workspace.")
        if not (path / ".git").is_dir() or (path / ".git").is_symlink():
            raise ValueError("Workspace must be an independently initialized Git repository.")
        if (path / ".git").resolve().parent != path:
            raise ValueError("Workspace Git metadata must remain inside the workspace.")
        return path

    def discover_workspaces(self) -> list[dict[str, str]]:
        """List direct children using the same validation applied at selection time."""
        if not self.workspace_root.is_dir():
            return []
        choices = []
        for path in sorted(self.workspace_root.iterdir()):
            try:
                approved = self.workspace(str(path.resolve()))
            except (OSError, ValueError):
                continue
            choices.append({"name": path.name, "path": str(approved)})
        return choices
