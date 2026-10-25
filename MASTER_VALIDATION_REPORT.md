# Operation Famiglia validation — 25 October 2026

Status: **PARTIAL — local implementation and acceptance checks passed; verified source publication and UI check pending**.
No percentages, fabricated logs or claim that all V2 milestones are finished.

## Baseline and environment

Fresh baseline command: installed Don-Codino `.venv/Scripts/python.exe -m pytest -q -W error
-rs -p no:cacheprovider --basetemp <isolated baseline directory>`: **67 passed, 3 skipped,
exit 0**, 68.90 seconds. Windows Python 3.14.6; FastAPI 0.162.0; Codex CLI 0.164.0,
authenticated with ChatGPT. Native Windows npm binary resolves successfully. Git 2.45.1.
Optional gh is absent. Database quick_check ok; additive schema version 2 in working copy.

Original historical calculator PASS was audited through live API, actual files, stored diff,
exit code and persisted check evidence. Its request omitted CLI requirements, so it was not
treated as full V2 calculator acceptance.

## Implementation checks so far

- First new V2 suite: **9 passed**, exit 0.
- Legacy regression caught FastAPI's lazy IncludedRouter breaking existing route introspection;
  concrete route registration fixed it without weakening that test.
- Intermediate regression: **75 passed, 3 skipped, 1 error**. The error was an unclosed SQLite
  connection in the new migration fixture under Python 3.14 warnings-as-errors. The fixture
  now explicitly closes it; final suite must confirm the correction.
- Original frontend behavior: **6 passed**, exit 0 after initial UI integration.
- Final suite, DON_DOCKER_TESTS=1: **89 passed, 2 skipped, exit 0, 61.93s**. Skips are the
  two Windows symlink-privilege tests; the actual Docker verifier test ran.
- Ruff check and format check: exit 0. JavaScript syntax exit 0. Prettier passed.
  Frontend tests: **7 passed, exit 0**. `pip check`: no broken requirements.

## Real calculator acceptance

Command: `python scripts/acceptance.py --execute --root <Toruk/artifacts/v2-acceptance>
--image don-codino-verifier:v2-validation` — **exit 0**.

Task `bf5d10d2120949cd920d81eaa7b2a78a`, plan `875222c267b84e2a90525ae0ff26312c`.
Workspace: `calculator-775a5520ee`, newly created disposable Git repository.
Actual Codex exit 0; created calculator.py and test_calculator.py. Independently read both:
arithmetic API, zero handling, argparse CLI, invalid argument/error exit coverage present.
Offline unprivileged verifier: **36 passed in 0.60s**, pytest exit 0; Ruff exit 0.
Independent separate read-only Codex review: exit 0, no actionable findings, model opinion
explicitly labeled. Static diff patterns found no high findings. Dependency vulnerability
audit is NOT RUN. Final task PASS, state VERIFIED, no repairs used. Invocation/session,
usage as actually reported, commands/timestamps/streams and changes are persisted.

Evidence: sibling Toruk `artifacts/v2-acceptance/calculator-775a5520ee-evidence.json`
and corresponding SQLite database. No generated tests were executed on the host.
No commit, push, PR, publish or merge occurred.

## Controlled failure and repair

Command: `python scripts/acceptance.py --execute --controlled-failure --root
<Toruk/artifacts/v2-repair-acceptance> --image don-codino-verifier:v2-validation`.
Disposable task `94eacb50b21746aabd257b862c799909`, workspace `calculator-ce0773e169`.
The harness changed the generated `add` implementation from addition to subtraction once
before real verification and recorded the intervention. Check one returned exit 1 with
**7 failed, 34 passed**; arithmetic and CLI result assertions exposed the defect. One
pre-approved repair ran. Codex exited 0 and the protected test/configuration hashes stayed
unchanged. Check two returned exit 0 with **41 passed**; Ruff also exited 0. The separate
read-only review exited 0 with no findings. Final status PASS, state VERIFIED, attempts=1.
Both failed and passing evidence remain persisted. No host test execution occurred.
Evidence: `artifacts/v2-repair-acceptance/calculator-ce0773e169-evidence.json`.

## Container builds

Clean `docker build --network=none -t don-codino-verifier:v2-validation verification`:
**exit 1**; package installation could not reach a registry with networking disabled.
This is not a clean-install pass.

`docker build --network=none -f verification/Dockerfile.runner-update
-t don-codino-verifier:v2-validation verification`: **exit 0**. Reused the already prepared
trusted local Python/pytest/Ruff image and replaced only the trusted entrypoint. Image
manifest list SHA-256 bce24e1115c89c4afee079641f91155ccfd6a764f6def4ce2c466d135e98e0a3.

## Packaging

Wheel build: `python -m pip wheel --no-deps --wheel-dir data/wheels .`: exit 0;
`don_codino-0.2.0a1-py3-none-any.whl`, SHA-256
`49bddbda665e4521203b58adc93631890c90d615fbe8d59b371565950cd02364`.
`scripts/package_smoke.py` installed that wheel and runtime dependencies into a new venv,
started the installed `app.main:create_app` factory on loopback, and verified `/health`,
`/`, `/static/app.js`, `/openapi.json`, and `/api/workspaces`: PASS, HTTP 200.

## Pending and limitations

Source publication and live V2 health/history checks passed. Visual UI inspection remains pending because no browser surface is available in this session. Windows symlink
privileges are unavailable. Live optional OpenAI planning and remote GitHub Actions have
not run. JS/TS verification, comprehensive dependency/security audits, durable scheduling,
automatic resume and gated remote Git automation remain incomplete. Whole V2 is not ready
for a release declaration.

## Published source validation

Applied 44 hash-checked source changes after stopping the verified localhost server (PID 33984). Source backup and SQLite online backup: `C:\Users\susee\VScode Project\Don-Codino\data\v2-backup-20261025-180840`. Preserved task/event rows: {'tasks': 4, 'events': 50}.

Restarted `C:\Users\susee\VScode Project\Don-Codino\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765` (PID 57944); /health returned HTTP 200 `{'status': 'ok', 'application': 'Don Codino'}`. Dashboard, static JS, OpenAPI and workspace routes returned HTTP 200. Persisted all 4 pre-existing task IDs; V2 diagnostics report DB quick_check ok and Codex available. The existing source database contained no repair task; real bounded-repair acceptance evidence was collected in the separate staged acceptance run.
