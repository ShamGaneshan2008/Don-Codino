# Operation Famiglia roadmap

See IMPLEMENTATION_STATUS.md for milestone-by-milestone status and exact next actions.
This increment delivers a tested local foundation, not the whole V2 release.

Next vertical slices, in dependency order:

1. Durable bounded queue, explicit safe retry and process-checkpoint recovery, including
   approved supported CLI resume. Never silently replay an approved/destructive operation.
2. Language-aware isolated verification profiles for JS/TS and richer Python checks,
   coverage/build/types and a pinned isolated dependency/security auditor.
3. Scope-aware repair planning and broader invariant protection, with real repair-limit
   failure acceptance and evidence of retained assertions.
4. Structured independent review findings persistence/resolution and deeper requirement
   coverage checks. Keep model opinion separate from verified evidence.
5. Gated dedicated branch/staging/commit/push/PR/CI integration. Address Git hooks/filters
   before running write operations against untrusted repositories. No autonomous merge.
6. Searchable/filterable dashboard, templates, queue controls, memory deletion UI and full
   settings/diagnostics. Preserve the current theme and keyboard accessibility.
7. Dependency audits, least-privilege pinned CI actions, type/coverage/build/security jobs,
   clean installation and all requested real acceptance scenarios before release readiness.
