# Agent 3 - Stock Counts Returns Residual Scout

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_3_stock_counts_returns_resid_scout_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`

Role: read-only scout for stock/counts/returns/residuals. You may write only your assigned closeout file.

Tasks:

- Verify the stock sequence remains INBOUND booking, counts, snapshot, clamps.
- Re-check that the manual count artifacts and OCR count draft exist.
- Identify known stock stoplines from prior dry-runs that the `PKT-STOCK` writer must handle, especially missing sizes, 3-in-1 quarantine, and Rombik XL negative replay.
- Re-baseline residual settlement count read-only and identify the exact dry-run command expected for `PKT-RESID`.
- Do not run apply paths. Do not mutate DB, repo files, LaunchAgents, workbooks, or external systems.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include source paths inspected and current stopline summary.
- Use `Gate: YELLOW` if stock is feasible but must quarantine/park known rows.
- Use `Gate: RED` only if required source artifacts are missing or contradictory.
