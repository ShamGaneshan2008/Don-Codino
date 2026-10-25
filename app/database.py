"""Small SQLite persistence layer; no shared connections across threads."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.records import Records


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store(Records):
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, prompt TEXT NOT NULL,
                    workspace TEXT NOT NULL, status TEXT NOT NULL, stage INTEGER NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT, exit_code INTEGER,
                    changed_files TEXT NOT NULL DEFAULT '[]', diff TEXT NOT NULL DEFAULT '',
                    verification TEXT NOT NULL DEFAULT '{"status":"NOT RUN"}',
                    message TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_workspace ON tasks(workspace)
                    WHERE status = 'RUNNING';
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE INDEX IF NOT EXISTS task_events ON events(task_id, id);
            """)
            self.migrate(db)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connection() as db:
            interrupted = [
                row["id"] for row in db.execute("SELECT id FROM tasks WHERE status='RUNNING'")
            ]
            for task_id in interrupted:
                previous = db.execute(
                    "SELECT state FROM task_details WHERE task_id=?", (task_id,)
                ).fetchone()["state"]
                db.execute(
                    "INSERT INTO transitions(task_id,previous,state,created_at,reason) "
                    "VALUES(?,?,'BLOCKED',?,'Interrupted server; no automatic resume')",
                    (task_id, previous, now()),
                )
                db.execute("UPDATE task_details SET state='BLOCKED' WHERE task_id=?", (task_id,))
                db.execute(
                    "INSERT INTO events(task_id,created_at,kind,message) "
                    "VALUES(?,?,'state','BLOCKED: interrupted execution')",
                    (task_id, now()),
                )
            db.execute(
                "UPDATE tasks SET status='BLOCKED', ended_at=?, message=? WHERE status='RUNNING'",
                (now(), "Server stopped before completion. Inspect the workspace before retrying."),
            )
            for task_id in interrupted:
                db.execute("UPDATE plans SET status='BLOCKED' WHERE task_id=?", (task_id,))

    def create(
        self,
        request: str,
        prompt: str,
        workspace: str,
        plan_id: str | None = None,
        revision: int | None = None,
    ) -> str:
        task_id = uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO tasks(id,request,prompt,workspace,status,stage,started_at) "
                "VALUES(?,?,?,?,'RUNNING',0,?)",
                (task_id, request, prompt, workspace, now()),
            )
            db.execute("INSERT INTO task_details(task_id,state) VALUES(?,'QUEUED')", (task_id,))
            if plan_id:
                self.bind_plan(db, plan_id, revision, task_id, prompt, workspace)
        return task_id

    def update(self, task_id: str, **fields):
        allowed = {
            "status",
            "stage",
            "ended_at",
            "exit_code",
            "changed_files",
            "diff",
            "verification",
            "message",
        }
        if not fields or not fields.keys() <= allowed:
            raise ValueError("Invalid task update")
        values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
        columns = ", ".join(f"{key}=?" for key in fields)  # only internal allowlisted columns
        with self.connection() as db:
            db.execute(f"UPDATE tasks SET {columns} WHERE id=?", [*values, task_id])  # noqa: S608
            if fields.get("status") in {"PASS", "FAIL", "BLOCKED", "CANCELLED"}:
                db.execute(
                    "UPDATE plans SET status=? WHERE task_id=?",
                    ("VERIFIED" if fields["status"] == "PASS" else fields["status"], task_id),
                )

    def event(self, task_id: str, kind: str, message: str):
        with self.connection() as db:
            db.execute(
                "INSERT INTO events(task_id,created_at,kind,message) VALUES(?,?,?,?)",
                (task_id, now(), kind, message[:16000]),
            )

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("changed_files", "verification"):
            result[key] = json.loads(result[key])
        return result

    def get(self, task_id: str):
        with self.connection() as db:
            return self.decode(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def list(self, limit: int = 50):
        with self.connection() as db:
            return [
                self.decode(row)
                for row in db.execute(
                    "SELECT * FROM tasks ORDER BY started_at DESC LIMIT ?", (limit,)
                )
            ]

    def events(self, task_id: str, after: int = 0):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM events WHERE task_id=? AND id>? ORDER BY id LIMIT 100",
                    (task_id, after),
                )
            ]
