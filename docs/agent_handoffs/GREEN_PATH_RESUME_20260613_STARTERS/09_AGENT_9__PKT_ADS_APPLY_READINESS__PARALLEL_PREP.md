# Agent 9 - PKT-ADS Apply Readiness Prep

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_9_pkt_ads_apply_readiness_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Web_automation/AGENTS.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. Agent 4 root closeout

Role: read-only prep agent for Kaspi-only `PKT-ADS`. You do not hold an AB or WA write lease.

Scope:

- Objective: make AB canonical ads backfill/restart apply-ready using the fresh WA watcher source.
- Allowed writes: only the assigned closeout file.
- Forbidden writes: AB DB, WA repo/data, docs, code, configs, browser login, Kaspi cabinet, Meta/Facebook/Instagram, LaunchAgents, and paid APIs.

Tasks:

- Re-baseline WA watcher freshness and AB canonical/sidecar freshness read-only.
- Locate the AB staging/backfill scripts, sidecar scripts, validators, env gates, dry-run/apply flags, and required source DB paths.
- Produce exact staging diff command, reconciliation command, apply command, rollback/backups, and validators for a future `PKT-ADS` writer.
- Explicitly confirm Meta/Instagram remains out of scope and no browser login is needed for the canonical backfill.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include source freshness, AB gap range, exact commands, validators, dirty-overlap risks, and human input requirement if any.
- Use `Gate: YELLOW` if WA dirty state requires serialization but AB canonical write is feasible.
- Use `Gate: RED` only if watcher source is stale/missing or canonical mapping cannot be staged.
