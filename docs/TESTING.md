# Testing and evidence

Use the project's installed Python (Windows: `.venv\Scripts\python.exe`).

```powershell
python -m pytest -q -W error -rs
python -m ruff check .
python -m ruff format --check .
npm test
npm run check
npm run format:check
python scripts/doctor.py
```

Trusted app tests use explicit fixtures for CLI/provider responses. These do not prove real
Codex execution. Integration tests cover plan revisions/strict approvals/atomic consumption,
database migration, state validation/recovery, inspection, protected repairs, streams,
request limits, locks, memory, independent review parsing and full versioned orchestration.

Set DON_DOCKER_TESTS=1 to run the existing actual offline verifier integration. Build its
image first. To refresh the trusted entrypoint without new package downloads when the
old local image is already prepared:

```powershell
docker build --network=none -f verification/Dockerfile.runner-update -t don-codino-verifier:v2-validation verification
```

Real calculator acceptance (separate disposable root, user-authorized actual CLI usage):

```powershell
python scripts/acceptance.py --execute --root C:/DisposableDonCodinoTests --image don-codino-verifier:v2-validation
```

Add `--controlled-failure` to document and inject one arithmetic defect between initial
coding and actual isolated verification. It changes addition to subtraction in calculator.py,
executes the real checks, allows one repair, and records both failure and subsequent result.
It never fabricates a check result or executes generated tests on the host. Reports and
SQLite evidence remain under the selected root. Files are not committed or published.

Checks record commands, directories, environment, timestamps, exit codes, separate streams,
truncation and parsed test-summary counts. Counts are parsed from real tool output. Model
review is explicitly opinion. Missing tools, unavailable isolation and unexecuted remote CI
remain separate limitations. See MASTER_VALIDATION_REPORT.md for actual outcomes.
