# Agent 3 - LINE31 Final Verify And Activation Controller

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_META_30MIN_RESCUE_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. Agent 1 closeout if available.
5. Agent 2 closeout if available.
6. This assigned starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent3_final_verify_activate_controller_closeout.md`

Task:

1. Wait for/read Agent 1 and Agent 2 closeouts.
2. Verify Agent 1 GREEN proves adset `120245481997290641` daily_budget is `3093`.
3. Verify Agent 2 GREEN proves exactly three LINE31 ads exist under the target adset.
4. Check whether exact owner approval for `LINE31_META_FINAL_ACTIVATE_ONLY_AFTER_BUDGET_AND_3ADS_VERIFIED` is present.
5. If approval is absent, do not activate. Produce YELLOW closeout with exact missing approval.
6. If approval is present and both dependencies are GREEN, activate only campaign `120245481137650641`, adset `120245481997290641`, and the exact three LINE31 ads.
7. Run read-only verification: campaign/adset/three ads active, adset daily_budget `3093`, landing URL `https://acmewear.pro/line31`, redirects and tracking still green.
8. Write launch closeout and local evidence under `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_final_launch_<timestamp>`.

Gate rules:

- GREEN only if activation was owner-approved and source-verified with repaired budget and exactly three active ads.
- YELLOW if dependencies are missing/YELLOW, approval absent, or verification incomplete.
- RED if any unrelated object changed or budget/ads do not match the approved shape.

Do not create ads, repair budget, change targeting, change bid strategy, deploy website, touch Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner publication, or internal Kaspi campaigns.
