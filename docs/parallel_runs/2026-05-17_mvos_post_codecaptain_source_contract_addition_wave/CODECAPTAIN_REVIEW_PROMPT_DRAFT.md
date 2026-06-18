# CodeCaptain Review Prompt Draft

Please review Agent874's post-CodeCaptain source-contract synthesis.

Current packet gate:

`Gate: YELLOW`

Question:

Can CodeCaptain accept this as a narrowed YELLOW post-addition packet and decide the remaining contracts needed before the next copied-temp proof attempt?

Boundary:

- DB SHA: `7e8b87a7eae6b208d38bce035f9a671f9e52a640f3f937d12f6951af64cbba32`
- CRM workbook SHA: `3edfeef46829cf0239a05c90444969bf2a36c64f2cda01186f87ce5219a9965e`
- PO dashboard SHA: `a95f31d778e73a60db1852a570d4c3dab3500ffa011064220086669bfc0917b4`
- Agent874 copied DB: `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/agent874_boundary_decision_copy.db`

Agent874 decision:

A full copied-temp MVOS materialization/proof rerun was not safe. No root lane is RED, but Agents868, 870, 871, and 872 remain YELLOW with blockers that would require invented truth or unaccepted contracts. Agent874 ran a bounded decision smoke only.

Root gates:

- Agent868 ads DirectAPI/Meta: YELLOW
- Agent869 payment evidence: GREEN
- Agent870 lifecycle cancellation: YELLOW
- Agent871 status-ledger scope/provenance: YELLOW
- Agent872 PO/day-complete: YELLOW
- Agent873 COGS route: GREEN

Key validator smoke:

- Source freshness strict: FAIL, eight requested-as-of rows missing.
- Policy gates strict: FAIL, six stored blockers.
- Ads sidecar readiness: FAIL, `ADS_CANONICAL_STALE`, `ADS_REFRESH_COVERAGE_MISSING`, max date `2026-05-11`.
- Day-complete: FAIL, `8797` eligible orders, `44` violations.
- PO dashboard: FAIL, `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK: sum(d_size)=9.5726 vs d_sku=10.0000`.
- Status ledger default: FAIL, `gap_count=5`.
- Status ledger scoped STOREB/ACMEWEAR/UNIVERSAL: FAIL, `gap_count=3`.
- Cashflow invariants and order cashflow coverage: PASS.
- COGS with Agent873 parent-unit CSV: PASS for copied-temp only.

Sub-decisions requested:

1. Ads: must Agent868 produce one contiguous current STOREB+ACMEWEAR DirectAPI packet through `2026-05-17`, or may partial evidence be retained with a YELLOW blocker? Is `META_FACEBOOK_OUT_OF_CURRENT_MVOS_SCOPE_NO_META_PUBLICATION_CLAIMS` accepted for copied-temp proof with no Meta publication claims?
2. Lifecycle: is `API_CANCELLING_NON_DELIVERED_EXPOSURE` accepted for the five retained `KASPI_DELIVERY/CANCELLING` rows without creating WebUI `status_change_at`?
3. Status ledger: may `MVOS_STATUS_LEDGER_SCOPE_STOREB_ACMEWEAR_UNIVERSAL_FOR_COPIED_TEMP_ONLY` be accepted, and may import-existing runs carry requested `--since/--until` into manifests when source hashes are recorded?
4. PO/day-complete: can Agent872's scoped retained-blocker contract be accepted, and what validator/doc change is required before copied-temp GREEN can be claimed?
5. If any of the above remain unaccepted, should the next proof be a deliberately YELLOW copied-temp board proof, or should proof be blocked until the lanes are made GREEN?

Files to review first:

1. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/AGENT874_SYNTHESIS_AND_PROOF.md`
2. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/agent874_synthesis_copied_temp_proof_closeout.md`
3. `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/root_closeout_matrix.csv`
4. `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/source_contract_matrix.csv`
5. `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/retained_blocker_matrix.csv`
6. `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/validator_results.tsv`
7. `~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554/agent874_synthesis_copied_temp_proof/oracle_pack_prioritized_files.txt`

Non-authorization:

This review prompt does not authorize production DB/workbook mutation, scheduler changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes, external account actions, owner publication, cash movement, PO commitment, stock change, price change, ad action, or production apply.
