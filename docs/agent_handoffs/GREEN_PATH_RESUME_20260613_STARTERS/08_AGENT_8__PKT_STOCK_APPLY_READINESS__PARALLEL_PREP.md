# Agent 8 - PKT-STOCK Apply Readiness Prep

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_8_pkt_stock_apply_readiness_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. Agent 3 root closeout

Role: read-only prep agent for `PKT-STOCK`. You do not hold a DB write lease.

Scope:

- Objective: make the required INBOUND -> count imports -> snapshot -> clamp-governance sequence executable by future serialized stock writers.
- Allowed writes: only the assigned closeout file.
- Forbidden writes: DB, source artifacts, workbooks, docs, code, configs, LaunchAgents, external systems, and paid APIs.

Tasks:

- Verify every stock source artifact path from OD-004/AMD-01/AMD-07 and Agent 3.
- Locate the scripts for PO arrival booking, count import/materialization, snapshot rebuild, stock validators, and their env gates.
- Build the exact internal sequence with dry-run commands, apply commands, expected backup requirements, and validators per step.
- Identify rows/families to park or quarantine before apply: LINE51 S, 3_in_1 men sets, Rombik XL negative replay, RUSH/T-SHIRT flags, direct CRM decrement risk.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include source-path census, exact command sequence, stoplines, quarantine/park list, validators, and whether human input is required.
- Use `Gate: YELLOW` if source artifacts exist but known rows must be parked.
- Use `Gate: RED` only if a required source artifact is missing or the sequence cannot be made governed.
