# Agent 6 - PKT-FX Apply Readiness Prep

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_6_pkt_fx_apply_readiness_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. Root closeouts from Agents 1, 2, 3, and 4

Role: read-only prep agent for `PKT-FX`. You do not hold a DB write lease.

Scope:

- Objective: make `PKT-FX` apply-ready for a later writer lane.
- Allowed writes: only the assigned closeout file.
- Forbidden writes: DB, docs, code, configs, workbooks, LaunchAgents, WA, external systems, and any paid API.

Tasks:

- Re-baseline `dim_fx_rates` freshness and schema read-only.
- Locate the current FX import/generation scripts, their env gates if any, dry-run/apply flags, and validator commands.
- Identify the single COGS authority files and all LINE52/v6/v7 constant consumers that `PKT-FX` would need to touch.
- Produce exact dry-run commands, exact apply commands, expected backup paths/gates, and tests for a future write-capable FX agent.
- Classify whether `PKT-FX` can run before or after `PKT-PROFIT`, `PKT-PRICE`, and `PKT-CASH`.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include commands run, current FX age/latest row, all touched future files, exact apply plan, validators, stoplines, and whether human input is required.
- Use `Gate: YELLOW` if sources are stale but a safe apply route exists.
- Use `Gate: RED` only if no governed FX apply route can be identified.
