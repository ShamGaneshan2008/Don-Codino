# Architecture

Local modular monolith; no Redis, PostgreSQL or frontend framework requirement.

`main.py` owns the factory, lifespan, same-origin protections, static files and legacy API.
`api_v2.py` supplies versioned planning, inspection, execution evidence, paginated history,
memory, diagnostics and read-only PR report routes. Routes are concrete APIRoutes for
compatibility with FastAPI route introspection. RequestLimits bounds mutation bodies.

`repository.py` enumerates bounded canonical files, excludes secrets/generated trees/links,
extracts selected Python AST imports/symbols and dependency names. It never runs repository
code. Context manifests record selected paths, bytes and SHA-256. Source bodies and package
scripts are not sent to the planning model. Large repositories are explicitly truncated.

`planning.py` validates a structured Plan, uses deterministic sections offline, or asks
the configured Responses API for strict JSON Schema output. Exact model input context
is recorded. Model errors never silently become a claimed AI success. Legacy enhance
still returns mode/prompt, augmented with persisted plan ID, revision and context.

`database.py`/`records.py` preserve tasks/events and add schema_migrations, plans,
plan_revisions, approvals, task_details, transitions and repository_memory. Revision
checks are optimistic; execution binding atomically consumes approval with task creation.
No SQLAlchemy migration is justified for this additive SQLite slice.

`workflow.py` runs approved work with workspace/database OS leases, a bounded concurrent
execution limit and persisted transitions. It captures every invocation and verification
attempt. Optional repairs stay in the original scope and stop if protected tests/configs
change. Capacity overflow is rejected, not silently queued. Startup blocks interrupted
tasks. Session IDs are recorded, but automatic CLI resume is not implemented.

`codex_runner.py` resolves native binaries, detects installed capabilities and passes
argument arrays plus stdin. `process.py` handles timeout/cancellation/tree cleanup and
bounded separate stdout/stderr. `verifier.py` supplies an offline unprivileged Docker
snapshot with no host mounts. The trusted container runner records commands/times/streams.

`reviewer.py` runs a separate read-only Codex process with a validated findings schema,
actual diff, bounded surrounding code and check evidence. High/critical unresolved findings
block the V2 task. `check_policy.py` provides conservative static diff checks and protected
repair hashes. These are not comprehensive vulnerability or dependency audits.

Memory stores only passing task provenance, evidence hashes and dependency signatures,
expires in 30 days and stays repository-specific. Retrieval supplies historical context,
never trusted instructions. The UI keeps its theme and adds context, repair opt-in,
workflow evidence and The Vault. Seven separately validated autonomous roles, a durable
queue, full Git publishing and broad language verification remain roadmap work.
