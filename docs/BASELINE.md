# Operation Famiglia baseline — 25 October 2026

Inspected before implementation: README, all root application modules, dashboard,
SQLite Store, configuration, tests, verifier entrypoint, and existing CI. No AGENTS.md
was present. Source repository is Don-Codino, not the Toruk working directory.

Existing factory: `app.main:create_app --factory`. Running application on loopback
port 8765 returns HTTP 200 for health/dashboard. Existing working features: same-origin
local API, allowlisted direct-child Git workspaces, explicit execution approval,
native Windows npm Codex resolution, stdin prompts, restricted subprocess execution,
cancellation/timeouts, Git changes, offline Docker pytest/Ruff, SQLite tasks/events,
SSE reconnect, and the existing gold/charcoal dashboard.

Baseline checks earlier in this session: pytest 67 passed, 3 skipped, exit 0;
Ruff passed, exit 0; frontend 6 passed, exit 0; JS syntax exit 0. Skips:
two Windows symlink privileges, one opt-in Docker test. These are historical
baseline measurements, not new V2 results.

Re-read stored contract a798e2325f0542ce9551827b9773f396 through the live API and
its evidence file: Codex exit 0; calculator.py, test_calculator.py, pyproject.toml;
32 pytest cases passed; Ruff exit 0. Independently read calculator.py. No CLI or
invalid-input tests exist. That recorded request omitted the CLI requirement.
Consequently this is real execution evidence, not completion of the full V2
calculator acceptance scenario. No new real coding execution has been performed.

Gaps: filename-only planning; no plan revisions/approval persistence; implicit
six-stage workflow; no session/usage parsing; no repairs; no independent review;
no repository memory; no GitHub operations; Python-only checks with sparse evidence.

Incremental plan: (1) bounded repository inspection and structured planning with
immutable revisions/approval linked to execution and UI context; (2) additive
SQLite migrations, state transition audit and execution metadata; (3) opt-in
bounded repairs with preserved failure evidence; (4) diagnostics, local review
evidence, provenance memory and continuation documentation. Keep all old endpoints.
Later milestones remain partial until their real acceptance requirements are met.

Implementation is prepared in an isolated working copy under Toruk/artifacts.
Original source/data are preserved. Publishing the tested files back to the sibling
repository requires sandbox write permission. No commit/push/merge is authorized.
