# Agent 71 - CodeCaptain Review Packet After Agent70

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_71_codecaptain_review_packet_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_71_evidence/`

Parallel group:

`agent71_codecaptain_review_packet`

## Mission

Prepare a CodeCaptain/designated review packet from the Agent70 combined current-baseline temp proof. The packet must ask whether Agent70's copied-temp proof is sufficient to draft a production repair/apply contract.

This is a packaging and review-preparation lane only. Do not perform production apply, do not ask the owner for authorization, do not mutate the live workbook, do not mutate schedulers, and do not write to external business systems.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT70_ORCHESTRATOR_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_combined_current_baseline_temp_proof_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/AGENT71_INPUTS.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/CODECAPTAIN_REVIEW_PACKET.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/VALIDATOR_BEFORE_AFTER.json`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/LEAKAGE_MATRIX.tsv`
12. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_70_evidence/TABLE_ROWCOUNT_MATRIX.tsv`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_71_codecaptain_review_packet_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_71_evidence/**`
- One flat Oracle/CodeCaptain review pack under `~/Docs/Oracle/Autonomous_business/2026-05-08/` with a timestamped task folder name.

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent70 evidence.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply.
- Do not ask owner for authorization.
- Do not activate Agent64.
- Do not reuse or request the old Agent54 owner phrase.
- Do not treat header-only rows as product truth.
- Do not hide or downgrade the `23` and `252` quarantine warnings.

## Required Work

1. Write a READCHECK in the closeout.
2. Verify Agent70's required evidence files exist and are internally consistent.
3. Verify the final Agent70 temp DB SHA/integrity if practical.
4. Summarize the exact Agent70 proof boundary:
   - temp DB path and SHA;
   - as-of date `2026-05-04`;
   - validators passed;
   - warning-only findings;
   - production/workbook untouched evidence;
   - leakage constraints.
5. Create a flat CodeCaptain review pack under:

   `~/Docs/Oracle/Autonomous_business/2026-05-08/<HHMMSS>_TASK-000_codecaptain-agent70-green-temp-proof-review/`

6. Keep total files in that pack at or below `16`.
7. Include one primary request markdown named clearly, for example:

   `CodeCaptain_Agent70_Green_Temp_Proof_Review_Request_20260508.md`

8. Include or copy only high-value sidecars that are needed for CodeCaptain to evaluate without guessing. Prefer Agent70 closeout, Agent70 CodeCaptain packet, validator summary, leakage matrix, row-count matrix, and manifest.
9. The request must ask CodeCaptain:
   - Is Agent70's combined copied-temp proof sufficient to draft a production repair/apply contract?
   - Are `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` and `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=252` acceptable visible warning classes?
   - What exact gates must be required before any owner phrase request?
   - What exact gates must be required before production apply?
   - Should the next lane be a production repair/apply contract draft, or a supplemental proof lane?
10. The request must explicitly forbid:
   - owner authorization request;
   - production apply;
   - Agent64 activation;
   - old Agent54 phrase reuse;
   - header-only rows as product truth;
   - hidden warning clearance;
   - Option C production automation.
11. Write a short `PACK_MANIFEST.md` in the Agent71 evidence folder listing every file in the Oracle pack and the source path it came from.
12. If safe and available, open the Oracle pack folder in Finder after creating it.

## Gate Semantics

`GREEN`:

- CodeCaptain review pack exists, is flat, has at most `16` files, and is ready for manual/external review.
- It preserves Agent70's proof boundary and stoplines.
- It does not mutate production, workbook, schedulers, external systems, or owner authorization state.

`YELLOW`:

- Pack is mostly prepared but a source/evidence supplement is required before external review.
- No unsafe mutation occurred.

`RED`:

- Pack weakens quarantine semantics, implies production apply, asks owner for authorization, activates Agent64, reuses old Agent54 phrase, fabricates source evidence, or mutates forbidden surfaces.
