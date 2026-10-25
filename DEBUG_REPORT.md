# Don Codino startup, workspace, and Codex verification

Verified on 25 October 2026, Windows, Python 3.14, Codex CLI 0.164.0.
The real calculator contract completed at 18:36:20 IST.

## Readiness verdict

**PASS for the requested end-to-end calculator workflow.** The existing application is
running at http://127.0.0.1:8765. Codex generated real files in the approved disposable
workspace; the restricted Docker verifier ran 32 passing tests and Ruff successfully.
SQLite contains the task, approved prompt, process events, changed files, diff, and verdict.

## Root causes and fixes

1. **Incorrect ASGI attribute:** `app/main.py` defines `create_app`, with the FastAPI
   instance local to that factory. `app.main:app` cannot import a module-level instance.
   The README and new VS Code launch configuration use `app.main:create_app --factory`.
   All existing routes and the application factory remain in place.
2. **Port binding:** the reported port-8000 error was avoided by binding explicitly to
   `127.0.0.1:8765`. The root cause of Windows denying the previous port was not established;
   no firewall, exclusion list, or system networking configuration was changed.
3. **Empty workspace selector:** `.env` pointed to `./workspaces`; the requested
   `calculator-test` folder was empty and lacked `.git`. The root is now
   `C:/DonCodinoWorkspaces`, and the existing empty folder was initialized with `git init`.
4. **Discovery depended on unrelated checks:** the frontend previously awaited history
   and `/api/settings`, including Codex/Docker probes, before populating options. It now
   calls `/api/workspaces` first. Discovery and selection share path validation, including
   resolved-path containment, direct-child membership, and local Git metadata checks.
5. **npm launcher rejected:** the adapter rejected `codex.cmd` without looking for its
   native executable. It now resolves known nested, hoisted, and legacy npm package
   layouts for Windows x64/ARM64. Shell launchers are never executed. Version,
   authentication, missing executable, timeout, and OS errors have useful diagnostics.
6. **Windows sandbox omitted:** `--ignore-user-config` also omitted the installed
   `windows.sandbox="elevated"` setting. The first actual execution reported a read-only
   environment and policy rejection. The adapter now explicitly selects this restricted
   Windows sandbox on Windows. `workspace-write`, denied escalation (`approval_policy="never"`),
   disabled agent-command network access, and ignored personal execpolicy rules remain intact.
7. **Verifier image missing:** Docker was available, but `don-codino-verifier:local` was
   absent. The existing `verification/Dockerfile` was built successfully (exit 0).

The Windows sandbox implementation is documented in the
[official Windows sandbox guide](https://learn.chatgpt.com/docs/windows/windows-sandbox).
The installed CLI's `exec --help` also confirmed the invocation flags used here.

## Exact local configuration

In `.env`:

```diff
-DON_WORKSPACE_ROOT=./workspaces
+DON_WORKSPACE_ROOT=C:/DonCodinoWorkspaces
```

`DON_CODEX_BINARY=codex` remains configured and works through native executable discovery.
The resolved executable on this machine is:

```text
C:\Users\susee\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe
```

An explicit `DON_CODEX_BINARY=C:/Users/susee/AppData/Roaming/npm/codex.cmd` is also supported
by the resolver; that wrapper is resolved to the native executable, not run through a shell.
Authentication from the actual Python backend returned `Logged in using ChatGPT`.
Prompt refinement used template mode; no OpenAI API key was needed or configured for this test.

## Correct Windows startup

Dependencies and the virtual environment are already installed locally.

```powershell
Set-Location "C:\Users\susee\VScode Project\Don-Codino"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. Stop a foreground server with Ctrl+C.
Use one worker and avoid reload during running contracts. VS Code's **Run Don Codino**
launch configuration uses this same factory and port. It requires the VS Code Python debugger.

The background server left running by this verification has listening PID **33984**.
To stop that instance before starting your own terminal session:

```powershell
Stop-Process -Id 33984
```

## Actual API verification

| Request/check | Actual result |
| --- | --- |
| Import `app.main:create_app` and instantiate | FastAPI instance; existing routes present |
| GET `/health` | HTTP 200; `{"status":"ok","application":"Don Codino"}` |
| GET `/` | HTTP 200; Don Codino themed dashboard HTML |
| GET `/static/app.js` | HTTP 200 |
| GET `/api/workspaces` | HTTP 200; `calculator-test` at `C:\DonCodinoWorkspaces\calculator-test` |
| GET `/api/settings` | HTTP 200; Codex available/authenticated; offline verification ready |
| POST `/api/prompts/enhance`, selected workspace | HTTP 200; template prompt generated |
| POST `/api/prompts/enhance`, `../` | HTTP 400 |
| POST `/api/prompts/enhance`, `C:/Windows` | HTTP 400 |
| POST `/api/tasks`, `approved: false` | HTTP 422 |
| POST `/api/tasks`, approved calculator plan | HTTP 201; real task started |
| GET completed task/history/diff | Completed task present; three files; 2,068-character diff |
| GET completed task events | HTTP 200; recorded events and `event: done` |
| Independent SQLite read | Stored final status `PASS` |

## Real end-to-end evidence

Request: Create a Python calculator supporting addition, subtraction, multiplication, and
division, including division-by-zero handling. Generate pytest tests and verify the implementation.

The user explicitly requested this disposable execution. The generated plan was reviewed
and submitted through the existing endpoint with `approved: true`; the application's
approval check was retained. No interactive CLI approval was required, and escalation remained denied.

Final task ID: `a798e2325f0542ce9551827b9773f396`.

- Workspace: `C:\DonCodinoWorkspaces\calculator-test`.
- Real Codex process exit: **0**.
- Real created files: `calculator.py`, `test_calculator.py`, `pyproject.toml`.
- Isolated pytest: **32 passed in 0.03s**, exit **0**.
- Isolated Ruff: **All checks passed!**, exit **0**.
- Final application verdict: **PASS**.
- Verification used the existing offline, read-only, unprivileged Docker configuration,
  with no host mounts, dropped capabilities, resource limits, and temporary workspace storage.

The earlier task `26a0bb9f71144e14a54cb7f7742b188a` remains recorded as **BLOCKED**:
Codex exited 0 but generated no files after a policy rejection; pytest exited 5 (no tests).
That failed attempt was not hidden or relabeled.

Local evidence:

- `data/calculator-e2e-plan.json`: generated plan.
- `data/calculator-e2e-result.json`: final API response including diff and verification.
- `data/calculator-e2e-events.txt`: actual persisted SSE event stream.
- `data/backend-test-results.txt`: final pytest output.
- `data/don-codino.sqlite3`: application history, including both real attempts.
- `data/server-8765.stderr.log`: current Uvicorn startup/access diagnostics.

## Regression tests and exit codes

| Command | Actual result | Exit |
| --- | --- | --- |
| `$env:DON_DOCKER_TESTS='1'; .\.venv\Scripts\python.exe -m pytest -q -W error -rs` | **68 passed, 2 skipped in 33.65s**; real Docker integration included | 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed | 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 23 files already formatted | 0 |
| `npm.cmd test` | **6 passed, 0 failed** | 0 |
| `npm.cmd run check` | JavaScript syntax valid | 0 |
| `npm.cmd run format:check` | Prettier checks passed | 0 |
| `git diff --check` | No whitespace errors | 0 |

New tests cover the ASGI factory and retained routes, Windows executable layouts and
architectures, native-only execution, subprocess failures, explicit Windows sandboxing,
workspace discovery/selection/revalidation, traversal, external Git metadata, frontend
discovery despite history failure, selected-path submission, and approval reset.

## Remaining limitations

- Two symlink security tests skipped because this Windows account cannot create symlinks
  without Developer Mode or the required privilege. Their assertions were retained;
  no test was weakened to pass. Other path validation tests and live rejection checks passed.
- The sandbox's separate Windows account encountered Git's dubious-ownership warning.
  Codex reviewed file contents directly and did not alter Git configuration. The backend,
  running as the workspace owner, successfully performed Git inspection and stored the diff.
- No connected browser was available for visual interaction. HTTP dashboard/assets checks
  and frontend behavior tests passed; a rendered browser dropdown was not visually inspected.
- Generated calculator files remain uncommitted for review. A subsequent contract in that
  workspace requires the user to commit or stash those changes, as enforced by existing checks.
- The ASGI factory startup was verified directly and over HTTP; the VS Code F5 debugger UI
  itself was not exercised.

## Files changed

- `.env` (local, Git-ignored): approved workspace root.
- `.vscode/launch.json`: correct factory, interpreter, working directory, and port.
- `app/config.py`: shared discovery and direct-child validation.
- `app/main.py`: dedicated discovery route; existing settings response retained.
- `app/static/app.js`: discovery call and workspace options before unrelated startup checks.
- `app/codex_runner.py`: native npm executable resolution, diagnostics, Windows sandbox selection.
- `tests/test_api.py`, `tests/test_security.py`, `tests/test_codex_runner.py`,
  `tests/frontend.test.mjs`: regression coverage.
- `README.md`: verified startup, workspace configuration, and CLI setup instructions.
- `DEBUG_REPORT.md`: this report.

No application rewrite, route removal, database replacement, GitHub push, or security bypass
was performed. The existing frontend theme and persistence/execution workflow are preserved.
