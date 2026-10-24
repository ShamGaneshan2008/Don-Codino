# Foundation review and verification record

Reviewed on 24 October 2026.

The starting repository contained one two-line README, one commit, no application, no tests,
and no workflow. There was no existing implementation to refactor or local CI error to reproduce.
GitHub's connected repository API returned no workflow runs for the initial commit.

The implementation separates configuration/path validation, SQLite persistence, subprocess
lifecycle, prompt refinement, the CLI adapter, read-only Git inspection, Docker verification,
orchestration, HTTP routes, and static UI assets. Dependencies are declared in pyproject.toml;
setuptools includes the static assets when packaging. No queue or database server is required.

Review addressed these concrete failure modes:

- Missing CLI or login records BLOCKED, with verification NOT RUN and no invented exit code.
- Incomplete verification, no collected tests, and no changed files cannot produce PASS.
- Workspace escapes, symlink escapes, source-repository execution, and dirty starts are rejected.
- A database constraint prevents concurrent writers even if two requests race during preflight.
- Windows process cleanup falls back to terminating the direct child when taskkill is restricted.
- Log emission buffers complete lines so secrets split across pipe reads are redacted together.
- Structured reports are redacted recursively, preserving valid JSON and numerical exit codes.
- Docker has no host mounts or network; bounded snapshots omit hidden files and external links.
- Docker readiness requires an actual server version, since this machine's CLI exits 0 for
  formatted info even when the daemon connection fails.
- Browser rendering uses textContent; approval clears when the plan or workspace changes.
- SSE consumes every persisted batch before closing and supports reconnection cursors.

Local evidence and environmental limits:

- Python 3.12.10 was installed into the ignored .tools folder because no Python was on PATH.
- FastAPI was started locally and GET /health returned status=ok.
- API tests cover validation, approval, history, logs, diffs, cancellation, origins, and Host checks.
- Workflow tests use explicit CLI/verification doubles. Subprocess tests launch real Python
  processes and exercise failure exit codes, timeout, cancellation, and split log lines.
- Real Codex 0.164.0-alpha.11.1 responds to --version and exec --help; login status reports
  Not logged in. A model-backed calculator generation cannot be verified in this session.
- Docker CLI exists, but the Docker daemon pipe is unavailable. Real isolated verification
  is skipped locally and configured as a CI job whose failures will fail the workflow.
- Creating symlinks requires privileges on this Windows account; that test is skipped here
  and runs on Ubuntu CI.
- The Browser runtime returned an empty browser list. Visual layout and interactive browser
  execution could not be checked here; static assets and UI/API contracts were checked locally.
- Optional OpenAI refinement is covered with a mocked Responses API payload; no live API call
  was made without an API key and explicit model configuration.
- Remote GitHub Actions has not run for these unpushed changes. No remote pass is claimed.

The calculator request was submitted to the actual running HTTP API in template mode. Its
persisted contract, `8c2cb2c18f404ac79523936bc2760da9`, correctly ended BLOCKED with
"Not logged in", no Codex exit code, no changed files, and verification NOT RUN. Its SSE stream
returned the recorded stages and verdict, then closed with a done event.

Latest local checks: **36 Python tests passed, 2 skipped; 4 frontend tests passed**. Ruff lint,
formatting, JavaScript syntax, and Prettier checks passed. The skips were Windows symlink creation and the opt-in real
Docker test. The Starlette test-client deprecation warning was subsequently resolved by adding
the documented `httpx2` development dependency. The full suite passes with `-W error`; CI now
uses the same warnings-as-errors check. Runtime prompt refinement continues to use httpx.
The contract persisted across a real server restart, and the homepage and JavaScript returned HTTP
200. The temporary verification server was stopped after these checks.

Follow-up testing reproduced and fixed four additional backend failures: credentials inside JSON
strings and nested sensitive dictionary fields were not redacted; an SSE stream could close before
delivering a verdict written during streaming; and a Docker warning before the report incorrectly
blocked otherwise valid verification. Regression tests now cover all four cases.

Frontend unit tests exercise the actual dashboard script with a small fake DOM. They verify that
refinement locks inputs and clears approval, failed refinement cannot reuse an approved plan,
late contract selections cannot replace the event stream, and older detail responses cannot
overwrite a newer verdict. They do not constitute a visual browser test. These tests run in CI.

Missing Git during task preflight now returns an actionable HTTP 503 instead of an uncaught 500,
without creating a task. Workflow verdict messages are redacted before being stored.

The follow-up live HTTP smoke test returned 200 for the homepage, health endpoint, API schema,
JavaScript, and CSS. Request validation, template enhancement, history, diffs, and complete SSE
delivery passed. Contract `cdc0f92cd67b46b3a33d6253ae7fc794` correctly recorded missing login as
BLOCKED. Codex remains unauthenticated. Docker Desktop startup was attempted, but its status and
daemon checks still reported unavailable; isolated execution remains unverified locally.

This is a local single-user MVP. Container verification covers Python projects using the image's
preinstalled dependencies. OS sandboxing and a disposable workspace are the execution boundary;
prompt constraints alone do not prove that an arbitrary repository or model-generated command is safe.
