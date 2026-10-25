# Operation Famiglia implementation status

V2 is **PARTIAL**. This file is a continuation contract, not a claim that all requested
deliverables exist. Baseline: docs/BASELINE.md. Actual commands/evidence: MASTER_VALIDATION_REPORT.md.
Legacy code, API and task history are preserved. No remote writes are authorized.

| Milestone | Status | Implemented / files | Tests and actual results | Remaining risks / next action |
|---|---|---|---|---|
| M0 Baseline | PASS | docs/BASELINE.md; inspected source, tests, config, DB and CI | Fresh baseline: 67 passed, 3 skipped; earlier frontend 6 passed and Ruff exit 0 | Historical calculator evidence lacks CLI; new acceptance separately recorded |
| M1 Stabilization | PARTIAL | main.py, locks.py, request_limits.py, diagnostics.py, scripts/doctor.py | Fresh wheel installed in a clean venv; actual factory/health/assets smoke passed; doctor found authenticated Codex and DB quick_check ok | Source update/restart and visual UI check pending |
| M2 Repository intelligence | PARTIAL | repository.py; bounded AST/manifests/symbols/context hashes, safe exclusion | FastAPI and JS fixtures passed in initial 9-test V2 suite | Heuristic selection; no complete dependency graph or general framework analysis |
| M3 Planning | PARTIAL | planning.py, prompt_engine.py, records.py, api_v2.py, dashboard | Revision/strict approval/atomic binding and strict Responses JSON schema tests passed with HTTP test double | Live optional OpenAI planning not run; refusal/large-repository coverage needed |
| M4 Codex | PARTIAL | codex_runner.py, execution_events.py, process.py | Real calculator Codex exit 0; real CLI help supports required flags/schema; separate stream tests added | Resume capability detected, actual resume not implemented; error taxonomy incomplete |
| M5 Orchestration | PARTIAL | state_machine.py, workflow.py, records.py, locks.py | Real persisted state sequence reached REVIEWING, SECURITY_CHECKING and VERIFIED; recovery, locks and duplicate consumption tests passed | No durable queue or safe automatic process resume; other declared states await their subsystems |
| M6 Verification | PARTIAL | verifier.py, process.py, verification/runner.py | Offline calculator: 36 tests; controlled failure: 7 failed/34 passed, then 41 passed; Ruff exit 0 for both | JS/TS, mypy, coverage and dependency vulnerability profiles absent |
| M7 Repair | PARTIAL | workflow.py, check_policy.py; opt-in up to two repairs, protected test/config hashes | Real one-repair acceptance passed; preserved test hashes; first pytest exit 1; retry pytest and Ruff exit 0 | Focused injected fault passed; general scope planner and all stop conditions need broader evidence |
| M8 Review | PARTIAL | reviewer.py, workflow.py; separate read-only process, validated findings | Real independent calculator review exit 0, no actionable findings | Model opinion is not proof; no findings resolution UI or comprehensive requirement checker |
| M9 GitHub | PARTIAL | diagnostics.py, api_v2.py; optional auth status and evidence PR report | gh unavailable on this machine; report integration tests added | Branch/staging/commit/push/PR/CI actions not implemented; remote writes require separate authorization |
| M10 Memory | PARTIAL | records.py, repository.py, planning.py; provenance/hash/signature/expiry/deletion | Memory isolation, dependency invalidation and deletion tests added | No complete category/procedure consolidation or architecture-revision invalidation |
| M11 Dashboard | PARTIAL | app/static/app.js, index.html; saved context, repair opt-in, Vault, detailed evidence | 7 frontend tests pass, including exact revision, approval and one-use execution; visual check pending | Full navigation, filtering, templates, scheduling and findings UX incomplete |
| M12 Security | PARTIAL | request_limits.py, locks.py, check_policy.py, security docs/tests | Existing path/origin/secret/cancel tests retained; new policy/limit/lease tests added | No comprehensive dependency audit or empirical prompt-injection guarantee; Windows symlink skips |
| M13 CI | PARTIAL | .github/workflows/ci.yml retains checks, adds pip consistency and wheel build | Local checks pass; remote workflow not run | Pin actions; add types/coverage/security checks and verify remote CI when available |
| M14 Evaluation | PARTIAL | scripts/acceptance.py; actual disposable coding, isolated checks, review, fault injection | Scenario A: Codex exit 0, 36 tests; deliberate failure: 7 fail, then repair, 41 pass; reviewer and Ruff exit 0 | Eight requested scenarios still lack full real acceptance evidence |
| M15 Release | PARTIAL | README, AGENTS, docs, validation/status; prerelease 0.2.0a1 | Offline wheel built and clean venv/server smoke passed; UI check pending | Whole V2 is not release-ready; complete remaining vertical slices before release |

## Next work, in order

Publish only tested changed files with SQLite/source backups, restart one loopback server,
verify existing history plus V2 routes, and inspect the actual dashboard. Record the
result in MASTER_VALIDATION_REPORT.md.

Then extend `app/workflow.py`, `app/state_machine.py`, `app/records.py` with a persisted
bounded queue and explicit safe retry/recovery, tested in `tests/test_v2.py`. Add isolated
JS/TS profiles and trusted dependency auditing in `app/verifier.py` / `verification/`,
with actual Docker tests. Build gated Git operations only after handling untrusted hooks
and filters, with per-action approvals and exact reviewed-diff binding. Never auto-merge.

No unfinished role, API, queue, scanner or Git operation should be described as implemented.
