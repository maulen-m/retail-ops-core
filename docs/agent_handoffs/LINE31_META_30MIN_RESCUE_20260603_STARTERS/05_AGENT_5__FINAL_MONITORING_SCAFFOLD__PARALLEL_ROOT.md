# Agent 5 - LINE31 Final Monitoring Scaffold

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_META_30MIN_RESCUE_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
5. This assigned starter prompt.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_meta_30min_rescue/agent5_final_monitoring_scaffold_closeout.md`

Task:

1. Prepare the post-launch monitoring packet scaffolding for the final LINE31 launch.
2. Include exact read-only verification checklist: campaign/adset/three ads active, adset daily_budget `3093`, website `/line31` 200, `/go/:color` redirects 302, signal events accepted, no fake purchase events accepted.
3. Include first-hour and next-morning decision gates, keeping Meta traffic, website event truth, redirect truth, and Kaspi order truth separated.
4. Do not perform live writes or claim launch success.
5. Write local evidence under `~/Docs/Autonomous_business/exports/validation/line31_meta_30min_rescue_monitoring_scaffold_<timestamp>`.

Gate rules:

- GREEN if final monitoring scaffold is complete and ready for Agent 3 after activation.
- YELLOW if required source paths are missing.
- RED if any external write was performed.

Do not create ads, repair budget, activate anything, change targeting, change bid strategy, deploy website, touch Kaspi/WebUI/API, price, stock, cash, supplier, PO, DB/workbook, scheduler/source-pointer, owner publication, or internal Kaspi campaigns.
