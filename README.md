# Don Codino

**The Godfather of Lazy Developers**

You give the orders. I make Codex an offer it can't refuse.

A local FastAPI application that turns an instruction into an editable coding plan, runs the
real Codex CLI after your approval, inspects the Git diff, verifies Python projects in an offline
Docker container, and keeps the evidence in SQLite. The charcoal, gold, and ivory dashboard
displays backend events and real results. Template refinement works without an API key.

## Operation Famiglia — V2 development increment

This is an incremental V2 foundation, not a completed V2 release. See
[implementation status](IMPLEMENTATION_STATUS.md), [actual validation](MASTER_VALIDATION_REPORT.md),
and [architecture](docs/ARCHITECTURE.md). Existing task history, factory and API remain.

The dashboard now saves repository-aware structured plans and context manifests, versions
edits, binds explicit approval to the exact prompt hash, and consumes approval atomically.
V2 contracts record explicit workflow transitions, invocation/session/usage evidence,
each verification attempt, a separate read-only Codex review and static security findings.
Repairs require a separate opt-in, maximum two; changing tests/check configuration during
repair blocks the contract. The Vault retrieves repository-specific verified outcomes,
with evidence provenance, dependency fingerprints and expiry. Run `python scripts/doctor.py`
for real local diagnostics. New endpoints are documented in [docs/API.md](docs/API.md).

The old `/api/tasks` interface keeps its original verification behavior and disables repairs.
Its PASS does not imply independent V2 review. Even V2 PASS is not release certification:
dependency auditing, broader language checks, full GitHub write automation, durable scheduling,
automatic resume and remote CI verification remain incomplete. No changes are committed,
pushed, published or merged automatically. See [testing](docs/TESTING.md) and
[security boundaries](docs/SECURITY.md) before running real contracts.

## Windows PowerShell setup

Install Python 3.12+, Git, and the native Codex CLI. Docker Desktop with Linux containers is
required for isolated verification. Node.js is needed only for frontend development checks.

```powershell
Set-Location "C:\Users\susee\VScode Project\Don-Codino"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
codex login
codex login status
docker build -t don-codino-verifier:local verification
```

If `py` is unavailable, install Python from python.org with the launcher enabled.
For the workspace-local portable runtime created during development, use
`.\.tools\python\python.exe` in place of `.\.venv\Scripts\python.exe`; no activation is needed.
The portable runtime and installed dependencies are ignored by Git.

For this Windows setup, set `DON_WORKSPACE_ROOT=C:/DonCodinoWorkspaces` in `.env`.
Create a disposable workspace once (the current `calculator-test` folder is already initialized):

```powershell
New-Item -ItemType Directory -Path C:\DonCodinoWorkspaces\calculator-test -Force
git -C C:\DonCodinoWorkspaces\calculator-test init
```

Start the office:

```powershell
Set-Location "C:\Users\susee\VScode Project\Don-Codino"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765>. Health: <http://127.0.0.1:8765/health>. API schema:
<http://127.0.0.1:8765/openapi.json>. Use **one worker**, without hot reload during active contracts.
Stop with Ctrl+C. Never bind this MVP to a public interface; it has no user authentication.

The ASGI entry point is the existing `create_app` factory in `app/main.py`. Use
`app.main:create_app --factory`; `app.main:app` fails because the module does not define a
global `app` instance. In VS Code, select **Run Don Codino** in Run and Debug (F5) to use
the same factory, local virtual environment, and port 8765.

## Your first contract

1. Select `calculator-test` as the territory.
2. Enter: “Build a Python calculator supporting addition, subtraction, multiplication, and
   division, with pytest tests including division by zero.”
3. Select **Refine the Plan**. Template mode uses the instruction, top-level filenames, fixed
   safety constraints, and acceptance criteria. It does not call an AI model.
4. Edit or copy the plan. Check the approval box and select **Make an Offer**.
5. Inspect the process log, changed files, verification report, and approved plan in The Evidence.
   Previous contracts remain in The Business after restarting the server.

Editing the request, workspace, or refined plan clears approval. A workspace must be clean before
execution. Commit or stash your own existing changes first. Cancellation preserves partial changes
and records them for inspection; it does not roll back your work. Review and commit changes yourself.

## Configuration

All settings are read from the environment or `.env` at startup. Restart after changing them.

For the local Windows workspace root, set this in `.env`:

```dotenv
DON_WORKSPACE_ROOT=C:/DonCodinoWorkspaces
```

Only direct child folders with their own `.git` directory appear in the selector. For example,
initialize `C:\DonCodinoWorkspaces\calculator-test` with `git init` if it is a new project.
The dashboard loads `GET /api/workspaces` independently of history and tool availability.
Selection is validated again by the backend; paths outside the root are rejected.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DON_WORKSPACE_ROOT` | `./workspaces` | Allowlisted root; direct child Git repositories appear in the selector |
| `DON_DATABASE` | `./data/don-codino.sqlite3` | Durable task history and events |
| `DON_CODEX_BINARY` | `codex` | Native executable name or absolute path |
| `DON_TIMEOUT_SECONDS` | `600` | Codex timeout, constrained to 10–3600 seconds |
| `DON_VERIFIER_IMAGE` | `don-codino-verifier:local` | Locally built Linux verification image |
| `OPENAI_API_KEY` | empty | Optional AI refinement credential |
| `DON_OPENAI_MODEL` | empty | Explicit Responses API model for AI refinement |

For real AI refinement, set **both** the API key and an available model ID. Only the request and
top-level filenames are sent to OpenAI; source contents are not uploaded by refinement. API failures
are reported, without silently claiming a successful AI result. Codex itself processes project
context as part of its normal operation and uses its own CLI login.

On Windows, npm `codex.cmd` / `codex.ps1` launchers are resolved to the native `codex.exe`
in known nested, hoisted, or legacy npm package layouts (x64 and ARM64). The shell wrapper
is never executed. `DON_CODEX_BINARY=codex` works when npm's launcher directory is on PATH;
an explicit launcher path or native executable path can also be configured. Missing platform
packages, failed version checks, and authentication failures produce actionable diagnostics.

The adapter explicitly selects `windows.sandbox="elevated"` because it ignores personal
configuration. This is the restricted Windows sandbox implementation, not a request to run
without isolation. If Windows sandbox setup requires interactive administrator approval,
complete the CLI's supported setup in your own terminal before running a contract. The app
keeps `approval_policy="never"` and never falls back to unrestricted execution. See the
[official Windows sandbox documentation](https://learn.chatgpt.com/docs/windows/windows-sandbox).

## Execution and verification boundaries

The adapter uses the documented [`codex exec` non-interactive interface](https://learn.chatgpt.com/docs/non-interactive-mode)
with JSON events, `workspace-write`, network disabled for agent commands, and
`approval_policy="never"`. This policy **denies** requests for sandbox escalation. It does not
approve dangerous commands. User config and execpolicy rules are ignored so permissive personal
settings cannot silently override these choices. Use a CLI version that supports these flags
(the integration was inspected against 0.164.0-alpha.11.1). Unsupported flags or unavailable OS
sandboxing fail visibly. The application never retries using unrestricted access.

- Workspaces must resolve inside the allowlisted root, including through symlinks. Git metadata
  must belong to the workspace. The Don Codino source repository and its ancestors are rejected.
- SQLite enforces one active contract per workspace. One server process owns execution; unfinished
  records become BLOCKED after restart. Check for orphaned processes after a forced server kill.
- Commands use argument arrays and stdin, without `shell=True`. Known secret formats and the
  configured API key are redacted before persistence. Redaction is best effort: do not put
  credentials in requests or project files. Saved logs and diffs remain sensitive local data.
- Prompt constraints forbid pushes, merges, commits, repository deletion, dependency installation,
  and host test execution. These instructions supplement the OS sandbox; they are not a separate
  command firewall. Use disposable or trusted workspaces and inspect the diff.
- Verification copies a bounded snapshot into an unprivileged container. No host directory,
  Docker socket, `.git` metadata, or hidden files are mounted. Network, Linux capabilities, and
  privilege escalation are disabled; CPU, memory, processes, time, and temporary storage are bounded.
  Python, pytest, and Ruff are preinstalled in the locally built image; no task-time downloads occur.
- The MVP verifies Python projects using pytest and Ruff. Extra project dependencies require a
  separately prepared trusted image. Hidden configuration files are intentionally excluded from
  verification. Projects requiring them need a reviewed extension to the snapshot policy.
- Legacy contracts have no automatic repairs. Revise the plan and explicitly approve a new contract after
  reviewing and committing or stashing the previous changes.

| Result | Meaning |
| --- | --- |
| `PASS` | Codex exited 0, changes exist, Git inspection completed, pytest and Ruff exited 0 |
| `FAIL` | Codex or an executed check failed |
| `BLOCKED` | Missing authentication, missing isolation/image, timeout, no tests, no changes, or incomplete inspection |
| `CANCELLED` | Cancellation was requested; partial changes may remain |
| `NOT RUN` | A verification step was never executed |

The verifier runs each check for at most 120 seconds, with an overall container limit of 300
seconds (or the configured task timeout, if smaller). Tests reporting no collected cases cannot
produce PASS. Test results show exit codes and bounded stdout/stderr. Passing tests do not replace
human review of behavior and the generated code.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Server health |
| GET | `/api/settings` | Safe configuration, dependencies, and approved workspaces |
| GET | `/api/workspaces` | Approved root and discovered direct child Git workspaces |
| POST | `/api/prompts/enhance` | `{request, workspace}` → editable prompt and actual refinement mode |
| POST | `/api/tasks` | `{request, workspace, prompt, approved: true}` → saved contract |
| GET | `/api/tasks?limit=50` | Most recent contracts, maximum 100 |
| GET | `/api/tasks/{id}` | Full record with verdict and verification |
| GET | `/api/tasks/{id}/events` | SSE; supports `Last-Event-ID` and `?after=` |
| GET | `/api/tasks/{id}/diff` | Changed files and captured diff |
| POST | `/api/tasks/{id}/cancel` | Request cancellation; send JSON `{}` |

POST requests require JSON. The browser uses same-origin requests; foreign origins and unexpected
Host headers are rejected. UI output is rendered as text, with a restrictive Content Security Policy.
Logs are bounded; events are persisted, streamed in batches, and resumed on reconnect. Large diffs
and individual log records are truncated. Dashboard totals represent the latest 100 contracts.

## Development and CI

```powershell
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
npm ci --ignore-scripts
npm test
npm run check
npm run format:check
```

For actual isolated calculator verification after starting Docker and building the image:

```powershell
$env:DON_DOCKER_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_verifier.py -q
Remove-Item Env:\DON_DOCKER_TESTS
```

GitHub Actions checks Python 3.12 and 3.13 on Ubuntu and Windows, runs Ruff, pytest, frontend
behavior tests, formatting, and JavaScript syntax checks. A separate Ubuntu job verifies a real
calculator project offline. Tests never need Codex credentials or an OpenAI key. Adapter/workflow
unit tests use explicit test doubles; the Docker integration test executes actual tools.

The initial checkout had only a README and no CI workflow. The GitHub connector returned no workflow
runs for its initial commit. The new workflow must be pushed and run before remote CI can be called
passing. This project does not push or deploy automatically.

See [the review record](docs/review.md) for local evidence and remaining verification limits.

## Resolving local prerequisites

The test extras include `httpx2`, the client recommended by
[Starlette](https://starlette.dev/testclient/), to avoid its deprecated httpx test-client fallback.
After updating dependencies, rerun `python -m pip install -r requirements.txt` with your project
Python. CI treats warnings as errors.

If Codex reports `Not logged in`, run `codex login` in your own terminal and complete the account
sign-in, then confirm `codex login status` succeeds. The app cannot sign in on your behalf.

For Docker, open Docker Desktop and complete any setup or startup prompts. Once the Linux engine
is running, `docker info` must report server details. Build the image with the command above, then
run the opt-in Docker tests. An installed Docker CLI alone does not provide isolation.

Windows symlink tests require Developer Mode or the appropriate Windows privilege. Enable that
through Windows settings if desired; the same security test runs without this requirement on
Ubuntu CI. Do not disable workspace validation to work around a skipped test.

Visual browser testing needs a connected browser. To verify remote CI, commit and push the local
changes to your GitHub repository, then inspect its Actions results. Local tests do not establish
that a remote workflow passed.
