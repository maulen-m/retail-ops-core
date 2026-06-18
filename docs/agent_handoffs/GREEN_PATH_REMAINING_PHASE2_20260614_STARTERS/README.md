# Green Path Remaining Phase 2 Starters

Purpose: re-baseline and continue the path-to-100%-green program after the owner-approved stock/C3/residual repairs.

Launch order:
1. Launch agents 1-4 in parallel. They are read-only and write only closeouts under `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/`.
2. The orchestrator reads all four closeouts and validates the current gates.
3. Launch agent 5 only after the orchestrator selects the next serialized write lane and confirms the AB lease scope.
4. Launch agent 6 only after Agent 5 closeout review.
5. Launch agent 7 only after Agent 6 closeout review; it is the narrow residual-settlement writer for the current 2026-06-14 10-row residual re-baseline.
6. Launch agent 8 only after Agent 7 closeout review if Agent 7 proves the exact-day scope is wrong but the corrected report window is still exactly the same 10 rows.
7. Launch agents 9-10 after Agent 8 closeout review. They are read-only scouts for shipped-freeze blockers and COGS authority blockers.

Starter folder:
`~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS`

Shared closeout folder:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2`
