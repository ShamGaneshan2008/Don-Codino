# Windows setup

Use Python 3.12+, Git and an authenticated supported Codex installation. Existing npm
codex.cmd/codex.ps1 wrappers resolve to the native executable in known package layouts;
the wrapper itself never receives untrusted shell text. Check `codex --version` and
`codex login status` in your own terminal. `python scripts/doctor.py` checks the backend's
actual native binary, capabilities, authentication, Git, DB, workspaces and isolation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
```

The factory is required. Port 49152 is another candidate if 8765 is unavailable; verify
availability instead of disabling the firewall. Use one worker without hot reload while
contracts run. Browser: http://127.0.0.1:8765; health: /health; schema: /openapi.json.

Set DON_WORKSPACE_ROOT to an approved root in .env. Its child projects require independent
.git directories. The source repository itself is not a contract target. Keep existing
workspaces/data. DO NOT recreate an existing .venv or overwrite .env without cause.
DON_MAX_ACTIVE_TASKS defaults to 2, bounded 1–4. Overflow is explicitly rejected.

Docker Desktop Linux containers are optional for planning/history but required for
automatic isolated verification. Build the trusted verifier before coding contracts.
No host-test fallback exists. GitHub gh is optional and its absence does not block local
coding. No OpenAI API key is required for deterministic planning or ChatGPT-authenticated CLI.
