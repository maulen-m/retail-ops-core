# Agent 32C - AB Copied-Temp Ads Rerun

Gate: `PENDING`

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md` if present
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. Agent 32A closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/agent32a_kaspi_marketing_current_packet_closeout.md`
6. Agent 32B closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/agent32b_meta_facebook_current_packet_closeout.md`
7. this prompt

## Hard Gate

Do not run unless Agent 32A and Agent 32B both closed `GREEN`.

If either source packet is missing, `YELLOW`, or `RED`, write a `YELLOW_DEPENDENCY_NOT_GREEN` closeout and stop.

## Task

Using a copied/temp DB only:

- materialize accepted current ads source packet evidence for `src_web_automation_kaspi_marketing_directapi`;
- materialize accepted current Meta source packet evidence for `src_facebook_ads_external_ads`;
- run `validate_policy_source_freshness.py` and `validate_policy_gate_results.py`;
- record whether `ads_source_truth` and `source_freshness` clear or remain blocked;
- preserve warning cohorts and retained non-ads blockers visibly.

Forbidden:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Facebook_ads writes;
- external fetches;
- Kaspi/API/WebUI mutations;
- ad-platform writes;
- ad spend, bid, budget, status, campaign changes;
- cash movement, PO commitment, stock or price changes;
- owner publication.

## Success Criteria

`GREEN` only if copied-temp validators pass for the assigned ads/source-freshness slice and protected surfaces remain unchanged.

If cashflow, stock, status-ledger, physical-stock, dirty-repo, or other non-ads blockers remain, keep them visible and do not call the full MVOS project green.

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/agent32c_ab_copied_temp_ads_rerun_closeout.md`
