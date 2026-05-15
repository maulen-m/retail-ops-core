# Agent 69D / Launcher ID 694 - Order-Entry Recovery As-Of Contract

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_order_entry_recovery_asof_contract_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_evidence/`

Parallel group:

`agent69de_root`

## Mission

Prove the safe way to apply the `758` recoverable order-entry rows exposed by Agent69B without creating as-of leakage or metadata ambiguity.

This is a bounded temp-DB/code-contract lane. You are not alone in the codebase; do not revert or overwrite unrelated edits by others.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT69ABC_ORCHESTRATOR_REVIEW_20260508.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_non_ads_operational_freshness_replay_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/AGENT70_INPUTS_69B.md`
9. `~/Docs/Autonomous_business/scripts/recover_order_entries_from_evidence.py`
10. `~/Docs/Autonomous_business/tests/test_recover_order_entries_from_evidence.py`

Primary temp DB input:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69b_evidence/agent69b_operational_freshness_working.db`

Expected input SHA256:

`d57e4ef24b3b05e736d54f6865c36405fc9a2c6668ac805e812e3d0dbe76c9f2`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_order_entry_recovery_asof_contract_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_69d_evidence/**`

Conditional code write set, only if tests prove the current contract is unsafe or ambiguous:

- `~/Docs/Autonomous_business/scripts/recover_order_entries_from_evidence.py`
- `~/Docs/Autonomous_business/tests/test_recover_order_entries_from_evidence.py`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not mutate `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not mutate Agent69B's input temp DB.
- Do not mutate scheduler state.
- Do not call live Kaspi/API/bank/Google/Meta/Web_automation/browser/external writes.
- Do not production-apply or ask owner for authorization.
- Do not invent product identity for unrecovered rows.

## Required Work

1. Write READCHECK into the closeout.
2. Copy the Agent69B temp DB into the Agent69D evidence folder.
3. Verify input SHA and copied DB integrity.
4. Reproduce Agent69B's order-entry recovery dry-run counts:
   - `target_validator_rows=1009`
   - `candidate_entry_rows=758`
   - `would_insert_entry_rows=758`
   - `quarantine_target_rows=275`
5. Inspect whether `updated_at` in `fact_order_entries_kaspi` is used as event truth by validators/materializers or is metadata only. Record evidence.
6. If the current recovery script needs an as-of-controlled timestamp contract, write a failing test first, then implement the smallest safe option, for example a `--recovery-ts` CLI parameter or equivalent function argument. The default behavior must remain compatible, and production writes must remain env-gated.
7. Apply the `758` recoverable entries only to the copied Agent69D temp DB.
8. Prove:
   - inserted rows equal the expected recoverable count or explain the deterministic reason for any difference;
   - no rows after `2026-05-04` are introduced as business facts;
   - execution timestamp does not contaminate pinned as-of validators;
   - remaining `ORDER_ENTRY_MISSING` rows are exactly the residual set for Agent695 to classify.
9. Run focused tests:

   ```bash
   python3 -m pytest tests/test_recover_order_entries_from_evidence.py -q
   ```

10. Run the relevant validator commands on the Agent69D temp DB and capture JSON:

   ```bash
   python3 scripts/validate_operational_stock_integration_gates.py --db <agent69d_temp_db> --as-of 2026-05-04 --json
   python3 scripts/validate_policy_source_freshness.py --db <agent69d_temp_db> --as-of 2026-05-04 --strict --json
   ```

11. Produce Agent70/Agent696 inputs:
   - exact command sequence;
   - whether code changed;
   - test result;
   - before/after counts;
   - remaining order-entry residual IDs/counts;
   - recommendation for the combined proof lane.

## Required Evidence Files

Create/populate:

- `READCHECK.md`
- `COMMANDS_RUN.md`
- `INPUT_SHA_AND_INTEGRITY.txt`
- `ORDER_ENTRY_RECOVERY_DRYRUN_BEFORE.json`
- `UPDATED_AT_CONTRACT_REVIEW.md`
- `TEST_RESULTS.txt`
- `ORDER_ENTRY_RECOVERY_APPLY_SUMMARY.json`
- `ORDER_ENTRY_RECOVERY_AFTER_VALIDATORS.json`
- `POST_ASOF_LEAKAGE_MATRIX.tsv`
- `RESIDUAL_ORDER_ENTRY_SET.tsv`
- `AGENT70_INPUTS_69D.md`
- `EVIDENCE_MANIFEST.txt`

## Gate Semantics

`GREEN`:

- the `758` recoverable rows are applied safely to the Agent69D temp DB or a deterministic equivalent count is proven;
- timestamp/as-of semantics are tested and no longer ambiguous;
- no production/external mutation occurred;
- remaining residual rows are isolated for Agent695.

`YELLOW`:

- the path is mostly proven but requires a separate implementation or review lane;
- the `758` count changes for a clear source-backed reason;
- no unsafe mutation occurred.

`RED`:

- production/external mutation occurs;
- recovery hides missing product identity;
- as-of leakage is introduced into business facts;
- tests fail without a safe explanation.
