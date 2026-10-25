# Threat model and security boundaries

The trusted user runs the local application and chooses direct-child Git workspaces.
Repository files, tests, build scripts, prompts, model output and package configuration
are untrusted. Protect host files, credentials, task history and the user's repositories.
This application is not a multi-user or remotely exposed service.

Canonical roots and native Git metadata are validated again before execution. Inspector
and reviewer skip symlinks/junctions and external paths. Secret-like files are identified
without reading their values. Planning sends bounded symbols/imports/dependency names,
not whole source trees. Logs and saved context are redacted. Redaction is best effort;
never place credentials in prompts. Diffs/history remain sensitive local data.

Native executable discovery avoids shell wrappers. Prompts use stdin; subprocesses use
argument arrays, a restricted inherited environment, timeouts and process-tree cleanup.
Codex uses workspace-write, denied escalation, ignored personal rules/configuration and
restricted Windows sandboxing. Review uses a new read-only context. Prompt restrictions
supplement OS sandboxing; they do not form a complete command firewall.

Unknown repository tests never run on the host. The verifier copies a bounded snapshot
into an unprivileged offline container with read-only root, temporary workspace storage,
resource limits, dropped capabilities and no mounts of host paths or Docker socket.
Dependencies must be in a separately prepared trusted image. Missing isolation is BLOCKED.
No container engine is needed to view history, inspect or plan locally.

Local origin/host protections, JSON validation, body limits and request IDs are enabled.
OS leases prevent a second application owner of a database and concurrent contract writers
in the same Git workspace. SQLite's partial index independently prevents duplicate active
tasks. Use a single server worker. Do not auto-resume interrupted tasks.

Repairs are explicit, bounded and preserve every failed check. Protected tests/config
hash changes during a repair block the task and preserve the partial changes for review;
there is no automatic rollback or permission to weaken assertions. A separate reviewer
checks actual changes. Static secret/bypass patterns are conservative and incomplete.
Dependency vulnerability auditing, exhaustive injection resistance, comprehensive secret
scanning and complete supply-chain verification are NOT established by these checks.

GitHub writes, commit automation and autonomous merging are not implemented in this slice.
Read-only gh status/report preparation cannot publish anything. Report vulnerabilities
privately to the repository owner; redact secrets from any reproduction or issue.
