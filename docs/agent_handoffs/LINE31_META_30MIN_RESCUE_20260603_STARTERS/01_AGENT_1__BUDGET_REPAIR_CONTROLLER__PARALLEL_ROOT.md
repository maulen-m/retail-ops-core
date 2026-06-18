# Agent 1 - LINE31 Budget Repair Controller

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_META_30MIN_RESCUE_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. This assigned starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent1_budget_repair_controller_closeout.md`

Task:

1. Verify read-only current state for campaign `120245481137650641` and adset `120245481997290641`.
2. Confirm campaign/adset are `PAUSED` and adset currently has `daily_budget=15000`.
3. Check whether exact owner approval for `LINE31_META_PAUSED_ADSET_BUDGET_REPAIR_ONLY` is present in the orchestrator handoff or a repo-local evidence file created by the orchestrator after owner paste.
4. If approval is absent, do not write. Produce YELLOW closeout with exact missing approval.
5. If approval is present, perform only this Meta write: update adset `120245481997290641` daily_budget to `3093`, keeping campaign/adset paused.
6. Verify read-only post-write: adset `daily_budget=3093`, campaign/adset still `PAUSED`.
7. Write local evidence under `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_budget_repair_<timestamp>`.

Gate rules:

- GREEN only if the budget repair was owner-approved, applied, and source-verified.
- YELLOW if approval is absent or Meta/API/UI blocks repair.
- RED if any unrelated object was changed or campaign/adset became active unintentionally.

Do not create ads, activate anything, change targeting, change bid strategy, deploy website, touch Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner publication, or internal Kaspi campaigns.
