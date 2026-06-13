# Agent 10 - PKT-PROFIT, PKT-QUAR, And PKT-RETURNS Readiness Prep

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_10_pkt_profit_quar_returns_readiness_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. Agent 2 and Agent 3 root closeouts

Role: read-only prep agent for later Phase 2 lanes that depend on line/stock truth. You do not hold a DB write lease.

Scope:

- Objective: make `PKT-PROFIT`, `PKT-QUAR`, and `PKT-RETURNS` exact enough for future serialized writers after `PKT-LINES`.
- Allowed writes: only the assigned closeout file.
- Forbidden writes: DB, docs, code, configs, workbooks, LaunchAgents, external systems, and paid APIs.

Tasks:

- Re-baseline COGS completeness, sales-chain max dates, quarantine counts, exception counts, and returns/QC tables read-only.
- Locate scripts, env gates, dry-run/apply flags, validators, and expected evidence outputs for the three lanes.
- Identify dependencies on `PKT-LINES`, `PKT-FX`, `PKT-STOCK`, and `PKT-CASH`.
- Produce exact dry-run/apply/validator commands for future writer lanes, and classify which can start immediately after Agent 5 versus which must wait.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include current baselines, dependencies, exact commands, validators, park/stopline conditions, and human input requirement if any.
- Use `Gate: YELLOW` if apply routes are feasible but must wait on dependencies.
- Use `Gate: RED` only if no governed route exists for a required lane.
