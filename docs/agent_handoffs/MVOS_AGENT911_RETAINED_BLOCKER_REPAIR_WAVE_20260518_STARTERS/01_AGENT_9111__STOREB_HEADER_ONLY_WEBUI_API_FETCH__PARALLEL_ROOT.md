# Agent911A / Transport Agent9111 - STOREB Header-Only WebUI/API Fetch

Gate target: `GREEN` if product identity evidence is found for the 15 STOREB orders, otherwise `YELLOW` with explicit retained quarantine.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT911_RETAINED_BLOCKER_REPAIR_WAVE_20260518_STARTERS/01_AGENT_9111__STOREB_HEADER_ONLY_WEBUI_API_FETCH__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/exports/validation/mvos_option1_next_repair_wave/agent910_copied_temp_contract_proof/AGENT910_COPIED_TEMP_CONTRACT_PROOF_CLOSEOUT.md`
7. `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`

## Assignment

Resolve the Agent910 order-entry freshness blocker for the 15 STOREB header-only orders, or prove that they must remain quarantined.

Order IDs:

```text
919726875
920305856
920417956
921817321
922014323
922556382
922880013
923474762
923497390
923672781
923721827
925297090
925568908
925671939
925988478
```

Owner-approved method:

- Use Computer Use / Chrome / read-only WebUI archive download or fetch if useful.
- Use existing API methods as fallback if they are read-only.
- If still header-only after read-only evidence search, keep them quarantined.

## Required Work

1. Verify starting protected boundary:
   - DB SHA `8d45d928888b0a03b42d8a2e73638a5f0ac30caa82b45943623e8df6433196d3`
   - workbook SHA `0dd9da0233fd30607b6f858db2ea7532bc9ec954021f5e9c195814a41d128313`
   - production DB integrity `ok`
2. Search local evidence first:
   - Agent905 evidence;
   - saved WebUI archive imports;
   - current CRM workbook evidence;
   - API raw order-entry archives.
3. If local evidence is insufficient, use read-only browser/API fetch:
   - STOREB only;
   - the 15 listed order IDs only;
   - no clicks that mutate WebUI state;
   - no external writes.
4. Produce a source-evidence manifest with SHA-256 for every fetched/downloaded file.
5. If identity-bearing product lines are found, build copied-temp SQL/JSON preview only and test it on a copied DB.
6. If identity-bearing product lines are not found, produce a retained-quarantine proof and a validator-contract recommendation.

## Outputs

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911a_storeb_header_only_webui_api_fetch_closeout.md`

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911a_storeb_header_only_webui_api_fetch_evidence`

Required artifacts:

- `SOURCE_EVIDENCE_MANIFEST.json`
- `STOREB_15_ORDER_EVIDENCE_MATRIX.tsv`
- `IDENTITY_BEARING_RECOVERY_PREVIEW.sql` if any identity-bearing rows are found
- `HEADER_ONLY_RETAINED_QUARANTINE_MATRIX.tsv`
- `VALIDATOR_RECOMMENDATION.md`
- command logs and boundary hashes

## Stoplines

- Stop `RED` if protected DB/workbook boundary changed before start.
- Stop `RED` if any WebUI/API action would mutate external state.
- Do not insert header-only rows into product truth.
- Do not production-apply anything.
