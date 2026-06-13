# Agent 7 - PKT-CASH And PKT-RESID Apply Readiness Prep

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_7_pkt_cash_resid_apply_readiness_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. Agent 2 and Agent 3 root closeouts

Role: read-only prep agent for `PKT-CASH` and `PKT-RESID`. You do not hold a DB write lease.

Scope:

- Objective: make cash anchor/rebuild and residual settlement apply-ready for later serialized writers.
- Allowed writes: only the assigned closeout file.
- Forbidden writes: DB, workbooks, docs, code, configs, LaunchAgents, external systems, and paid APIs.

Tasks:

- Verify the owner-provided cash snapshot artifact path exists and can be read without modification.
- Re-baseline current `cashflow_cash_anchor`, cashflow event freshness, and residual candidate count/sum read-only.
- Locate the cash anchor script, residual settlement script, env gates, dry-run/apply flags, and validators.
- Produce exact dry-run commands, exact apply commands, expected backup requirements, rollback instructions, and validator commands for future write agents.
- Identify whether `PKT-RESID` can safely run before the full `PKT-CASH` anchor, or should wait.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include current cash anchor age, snapshot artifact read status, residual count/sum, commands, validators, stoplines, and human input requirement if any.
- Use `Gate: YELLOW` for apply-ready but owner-workbook/cash divergence caveats.
- Use `Gate: RED` only if the required snapshot artifact is missing or contradictory.
