"""Run from any directory: python scripts/doctor.py. Read-only integration checks."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.diagnostics import report  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(asyncio.run(report(Settings.from_env())), indent=2))
