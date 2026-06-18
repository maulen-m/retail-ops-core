# Agent876 Starter: Ads Current Source Refresh

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent876_ads_current_source_refresh_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent876_ads_current_source_refresh_evidence`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_owner_qa_repair_wave/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_owner_qa_repair_wave/agent875_contract_registry_closeout.md`
9. this starter prompt.

## Assignment

Produce read-only current ads source evidence for the owner-QA MVOS repair wave.

You may read `~/Docs/Autonomous_business`, `~/Docs/Web_automation`, `~/Docs/Business_3/Facebook_ads`, and existing local evidence. You may run existing read-only API/fetch commands. Use existing API methods first. If those fail or are incomplete, you may use Chrome Auto Connect or headless Playwright only as a read-only fallback.

Required coverage:

- STOREB Kaspi Marketing through `2026-05-17`, fetched through `UNIVERSAL` login/switcher.
- ACMEWEAR Kaspi Marketing through `2026-05-17`.
- Meta/Facebook evidence for `2026-05-13..2026-05-17`.

Write only to your assigned evidence folder and assigned closeout. Do not edit repo files.

Do:

- Record exact commands, source paths, date windows, store identities, access identities, campaigns/products found, and SHA-256 hashes of evidence files.
- Preserve STOREB business identity separately from `UNIVERSAL` access identity.
- Keep any known positive spend visible.
- Run read-only ads validators if safe and relevant.
- State whether copied-temp proof may materialize ads source-freshness rows from your evidence.

Do not:

- mutate Web_automation;
- write to Kaspi, Meta/Facebook, or any ad platform;
- change bids, budgets, prices, stock, DB, workbook, scheduler, source pointers, or external accounts;
- infer missing spend as zero;
- publish owner-facing claims.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- coverage matrix by source/store/date;
- exact evidence paths and hashes;
- commands run and exits;
- remaining blockers or CodeCaptain questions.
