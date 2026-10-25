"""Additive V2 persistence. Existing task and event tables remain compatible."""

import hashlib
import json
from uuid import uuid4

from app.state_machine import validate

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, request TEXT NOT NULL,
 mode TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
 created_at TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
 structured TEXT NOT NULL, context TEXT NOT NULL, task_id TEXT REFERENCES tasks(id));
CREATE TABLE IF NOT EXISTS plan_revisions(
 plan_id TEXT NOT NULL REFERENCES plans(id), revision INTEGER NOT NULL,
 prompt TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(plan_id,revision));
CREATE TABLE IF NOT EXISTS approvals(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id),
 revision INTEGER NOT NULL, sha256 TEXT NOT NULL, approved_at TEXT NOT NULL,
 UNIQUE(plan_id,revision));
CREATE TABLE IF NOT EXISTS task_details(
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), state TEXT NOT NULL,
 plan_id TEXT REFERENCES plans(id), revision INTEGER, session_id TEXT,
 usage TEXT NOT NULL DEFAULT '{}', attempts INTEGER NOT NULL DEFAULT 0,
 evidence TEXT NOT NULL DEFAULT '[]', invocation TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS transitions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id),
 previous TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS repository_memory(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id),
 summary TEXT NOT NULL, evidence_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, fingerprint TEXT NOT NULL, UNIQUE(task_id));
"""


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Records:
    def remember(self, task_id, fingerprint):
        from datetime import UTC, datetime, timedelta

        from app.database import now

        task = self.get(task_id)
        execution = self.execution(task_id)
        checks = task["verification"]
        if (
            task["status"] != "PASS"
            or task["exit_code"] != 0
            or any(checks.get(name, {}).get("exit_code") != 0 for name in ("tests", "lint"))
        ):
            raise ValueError(
                "Only outcomes with passing execution and check evidence may be learned"
            )
        evidence_hash = digest(json.dumps(execution["evidence"], sort_keys=True))
        expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO repository_memory VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    task["workspace"],
                    task_id,
                    task["request"][:2000],
                    evidence_hash,
                    now(),
                    expires,
                    fingerprint,
                ),
            )

    def memories(self, workspace, fingerprint):
        from app.database import now

        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM repository_memory WHERE workspace=? AND fingerprint=? "
                    "AND expires_at>? ORDER BY created_at DESC LIMIT 20",
                    (workspace, fingerprint, now()),
                )
            ]

    def forget(self, memory_id, workspace):
        with self.connection() as db:
            return bool(
                db.execute(
                    "DELETE FROM repository_memory WHERE id=? AND workspace=?",
                    (memory_id, workspace),
                ).rowcount
            )

    def migrate(self, db):
        from app.database import now

        db.executescript(SCHEMA)
        db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?)", (now(),))
        # Legacy completed records keep their verdict. Interrupted writers are recovered at startup.
        db.execute("""INSERT OR IGNORE INTO task_details(task_id,state)
                      SELECT id,CASE status WHEN 'PASS' THEN 'VERIFIED' WHEN 'FAIL' THEN 'FAILED'
                      WHEN 'RUNNING' THEN 'EXECUTING' ELSE status END FROM tasks""")

    def create_plan(self, request, workspace, mode, provider, model, prompt, structured, context):
        from app.database import now

        plan_id, created = uuid4().hex, now()
        with self.connection() as db:
            db.execute(
                "INSERT INTO plans VALUES(?,?,?,?,?,?,?,1,'AWAITING_PLAN_APPROVAL',?,?,NULL)",
                (
                    plan_id,
                    workspace,
                    request,
                    mode,
                    provider,
                    model,
                    created,
                    json.dumps(structured),
                    json.dumps(context),
                ),
            )
            db.execute(
                "INSERT INTO plan_revisions VALUES(?,1,?,?,?)",
                (plan_id, prompt, digest(prompt), created),
            )
        return self.plan(plan_id)

    def plan(self, plan_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["structured"] = json.loads(result["structured"])
            result["context"] = json.loads(result["context"])
            result["revisions"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM plan_revisions WHERE plan_id=? ORDER BY revision", (plan_id,)
                )
            ]
            result["prompt"] = result["revisions"][-1]["prompt"]
            result["approvals"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM approvals WHERE plan_id=? ORDER BY approved_at", (plan_id,)
                )
            ]
            return result

    def revise_plan(self, plan_id, expected, prompt):
        from app.database import now

        with self.connection() as db:
            changed = db.execute(
                """UPDATE plans SET revision=revision+1,
                status='AWAITING_PLAN_APPROVAL' WHERE id=? AND revision=? AND task_id IS NULL
                AND status IN ('AWAITING_PLAN_APPROVAL','APPROVED')""",
                (plan_id, expected),
            ).rowcount
            if not changed:
                raise ValueError("Plan changed or execution already began; reload before editing.")
            db.execute(
                "INSERT INTO plan_revisions VALUES(?,?,?,?,?)",
                (plan_id, expected + 1, prompt, digest(prompt), now()),
            )
        return self.plan(plan_id)

    def approve_plan(self, plan_id, expected):
        from app.database import now

        with self.connection() as db:
            changed = db.execute(
                """UPDATE plans SET status='APPROVED' WHERE id=? AND revision=?
                AND task_id IS NULL AND status='AWAITING_PLAN_APPROVAL'""",
                (plan_id, expected),
            ).rowcount
            if not changed:
                raise ValueError("Plan changed or already approved; reload the current revision.")
            revision = db.execute(
                "SELECT sha256 FROM plan_revisions WHERE plan_id=? AND revision=?",
                (plan_id, expected),
            ).fetchone()
            db.execute(
                "INSERT INTO approvals VALUES(?,?,?,?,?)",
                (uuid4().hex, plan_id, expected, revision["sha256"], now()),
            )
        return self.plan(plan_id)

    def bind_plan(self, db, plan_id, revision, task_id, prompt, workspace):
        changed = db.execute(
            """UPDATE plans SET task_id=?, status='EXECUTING'
            WHERE id=? AND revision=? AND status='APPROVED' AND task_id IS NULL AND workspace=?
            AND EXISTS(SELECT 1 FROM approvals a JOIN plan_revisions r
             ON a.plan_id=r.plan_id AND a.revision=r.revision AND a.sha256=r.sha256
             WHERE a.plan_id=plans.id AND a.revision=plans.revision AND r.sha256=?)""",
            (task_id, plan_id, revision, workspace, digest(prompt)),
        ).rowcount
        if not changed:
            raise ValueError("The exact current plan revision must be approved and unused.")
        db.execute(
            "UPDATE task_details SET plan_id=?,revision=? WHERE task_id=?",
            (plan_id, revision, task_id),
        )

    def transition(self, task_id, target, reason=""):
        from app.database import now

        with self.connection() as db:
            previous = db.execute(
                "SELECT state FROM task_details WHERE task_id=?", (task_id,)
            ).fetchone()["state"]
            validate(previous, target)
            db.execute(
                "INSERT INTO transitions(task_id,previous,state,created_at,reason) "
                "VALUES(?,?,?,?,?)",
                (task_id, previous, target, now(), reason[:2000]),
            )
            db.execute(
                "UPDATE task_details SET state=? WHERE task_id=? AND state=?",
                (target, task_id, previous),
            )
            db.execute(
                "INSERT INTO events(task_id,created_at,kind,message) VALUES(?,?,'state',?)",
                (task_id, now(), target),
            )

    def metadata(self, task_id, **fields):
        allowed = {"session_id", "usage", "attempts", "evidence", "invocation"}
        if not fields or not fields.keys() <= allowed:
            raise ValueError("Invalid execution metadata")
        values = [
            json.dumps(value) if isinstance(value, (dict, list)) else value
            for value in fields.values()
        ]
        columns = ",".join(f"{key}=?" for key in fields)
        with self.connection() as db:
            db.execute(
                f"UPDATE task_details SET {columns} WHERE task_id=?",  # noqa: S608
                [*values, task_id],
            )

    def execution(self, task_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM task_details WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for name in ("usage", "evidence", "invocation"):
                result[name] = json.loads(result[name])
            result["transitions"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM transitions WHERE task_id=? ORDER BY id", (task_id,)
                )
            ]
            reviews = [
                item.get("report", {})
                for item in result["evidence"]
                if item.get("kind") == "review"
            ]
            result["readiness"] = {
                "human_review": "READY"
                if result["state"] == "VERIFIED" and reviews and reviews[-1].get("status") == "PASS"
                else "BLOCKED",
                "release": "NOT ASSESSED",
                "limitations": [
                    "Dependency vulnerability audit and remote CI are separate checks.",
                    "A model review is an opinion, not proof of requirement coverage.",
                ],
            }
            return result
