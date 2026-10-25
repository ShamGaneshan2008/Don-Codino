# API

Run on localhost. OpenAPI: `/openapi.json`. Existing `/health`, `/api/settings`,
`/api/workspaces`, `/api/prompts/enhance`, `/api/tasks` and task detail/diff/events/cancel
routes remain. POST requires application/json; mutation bodies are limited to 128 KB.
Errors use FastAPI `detail`; responses carry an application-generated X-Request-ID.

| Method | Versioned path | Behavior |
|---|---|---|
| GET | /api/v1/workspaces/inspect?selection=...&request=... | Canonical inspection and Git status |
| POST | /api/v1/plans | `{request, workspace}`; saved structured plan/context/prompt |
| GET | /api/v1/plans/{id} | All revisions and approvals |
| POST | /api/v1/plans/{id}/revisions | `{revision, prompt}`; creates next revision, clears approval |
| POST | /api/v1/plans/{id}/approve | `{revision, approved: true}`; exact current revision |
| POST | /api/v1/plans/{id}/execute | `{revision, approved: true, max_repairs: 0}`; consumes approval |
| GET | /api/v1/tasks?limit=25&offset=0 | Paginated tasks and total |
| GET | /api/v1/tasks/{id}/execution | State transitions, session, usage, all attempt evidence |
| GET | /api/v1/tasks/{id}/logs?after=0 | Up to 100 events and next_cursor |
| GET | /api/v1/tasks/{id}/pr-report | Actual evidence report; no remote write |
| GET | /api/v1/memory?selection=... | Current matching verified outcomes |
| DELETE | /api/v1/memory/{id}?selection=... | Delete one outcome in that workspace |
| GET | /api/v1/system/readiness | Codex, isolation, DB readiness |
| GET | /api/v1/system/diagnostics | Full safe local integration diagnostics |
| GET | /api/v1/github/status | Optional gh installation/authentication only |

Repair allowance is an integer 0–2, default 0. The explicit execution request authorizes
that allowance and records it in invocation evidence. Tests/configuration changes during
repair block execution. Editing a saved plan produces a new revision and invalidates any
earlier approval. A consumed plan cannot be edited or executed again. Revisions/races
return 409, invalid workspace 400, validation 422, missing record 404, unavailable launch
503. No arbitrary command or arbitrary filesystem endpoint exists.

The legacy task status remains RUNNING/PASS/FAIL/BLOCKED/CANCELLED for compatibility.
`execution.state` supplies the explicit V2 state. SSE uses persisted event IDs and supports
Last-Event-ID. `execution.readiness` separates human-review eligibility from release
readiness; dependency audit and CI are separate evidence, not implicit success.
