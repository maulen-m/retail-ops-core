# Agent861 Starter: Ads Source Truth

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent861_ads_source_truth_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent861_ads_source_truth`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Assignment

Resolve or narrow ads source truth blockers for copied-temp MVOS proof.

You may read `~/Docs/Web_automation` and `~/Docs/Business_3/Facebook_ads`. You may perform read-only API/source fetches if existing repo methods support them and they are needed. You may write only to your assigned evidence folder and assigned closeout.

Do:

- Inspect current blockers for `src_facebook_ads_external_ads` and `src_web_automation_kaspi_marketing_directapi`.
- Verify whether STOREB, ACMEWEAR, and required Meta/Facebook evidence for the current window can be made source-fresh for copied-temp proof.
- Preserve positive spend; never treat unmapped positive-spend rows as zero spend.
- Reuse Agent855 `11956144b -> CL_OC_MEN_LINE52_BLACK` only as copied-temp evidence if source-backed.
- If read-only live fetch succeeds, store sanitized local evidence and commands.
- Run relevant ads validators on copied or read-only surfaces where safe.

Do not:

- mutate Web_automation;
- write to ad platforms;
- change bids, budgets, campaigns, prices, stock, DB, workbook, or schedulers.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- exact date/store/campaign/product coverage;
- source freshness recommendation for copied-temp proof;
- any remaining CodeCaptain questions.
