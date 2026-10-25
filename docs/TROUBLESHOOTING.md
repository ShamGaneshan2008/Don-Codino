# Troubleshooting, backup and recovery

`Attribute app not found`: use `app.main:create_app --factory`; do not replace the factory.
WinError 10013: inspect used/reserved ports and choose another loopback port. Do not disable
the firewall or terminate unrelated processes.

Missing Codex/platform package: run scripts/doctor.py. Configure DON_CODEX_BINARY to a
native executable or known npm Codex launcher. Unsupported flags block V2 execution.
Authentication is checked by the backend. Complete login yourself; never paste credentials
into a contract. Missing gh is an optional integration limitation.

No workspace options: initialize a clean independent child Git repository beneath the
configured root. Traversal, external paths and invalid Git metadata remain rejected.
Commit or stash your own changes manually before a new contract. A second writer or server
owner receives a lock error; a crashed process's OS lease is released automatically.

Restart with unfinished work: it becomes BLOCKED with transition evidence. Inspect partial
changes and orphaned processes before approving a new plan. Automatic destructive resume
and silent rollback are not implemented. Cancellation preserves inspectable partial changes.

Missing Docker/image/dependencies: verification is BLOCKED. Build a trusted image; never
run unknown tests directly on the host. A build using --network=none needs cached/prepared
dependencies. The runner-update Dockerfile can reuse the existing trusted local image.

Before migrating, use SQLite's online backup API (safe while the application is idle/running):

```python
import sqlite3
from contextlib import closing

with closing(sqlite3.connect("data/don-codino.sqlite3")) as source:
    with closing(sqlite3.connect("data/don-codino-backup.sqlite3")) as destination:
        source.backup(destination)
```

Keep source and DB backups together, outside Git. Stop the server before recovery. Restore
the reviewed source backup and corresponding SQLite backup, then start one worker and check
health/history. Do not copy only a live WAL-mode .sqlite3 file and assume it is a complete
backup. V2 migrations add tables and preserve existing task/event content.
