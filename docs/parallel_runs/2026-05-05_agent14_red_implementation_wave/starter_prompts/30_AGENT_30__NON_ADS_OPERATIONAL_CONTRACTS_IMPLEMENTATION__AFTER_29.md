# Agent 30 - Non-Ads Operational Contracts Implementation

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_non_ads_operational_contracts_implementation_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_28_29.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_non_ads_operational_residual_temp_proof_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/non_ads_resolution_matrix.json`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/before_after_residual_counts.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/validation_matrix.json`
9. this starter prompt

## Mission

Implement the minimum repo-code/test contracts required to clear the remaining non-ads operational blockers on a fresh temp DB. Do not write production `db/app.db`; this is implementation plus temp proof only.

## Write Boundary

Allowed:

- non-ads operational code/tests/docs needed for the contracts below;
- assigned closeout and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_30_evidence/`.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- ad-platform writes;
- Web_automation writes;
- ads canonical reader rewrites unless a small compatibility import is strictly necessary;
- broad refactors;
- weakening validators or publication gates.

## Required Implementation Lanes

1. Order-entry:
   - Preserve Agent 29's safe recovery behavior for the `736` `CURRENT_CRM`-backed validator rows.
   - Keep the `276` STOREB header-only rows quarantined unless real item-entry evidence is recovered from approved source paths.
   - Add a regression test proving header-only rows do not clear product-level stock/profit publication.

2. Lifecycle:
   - Add an explicit tested source contract for same-store `fact_orders_kaspi` header evidence only when:
     - `internal_status=COMPLETED`
     - `kaspi_status=ARCHIVE`
     - `kaspi_status_detail=COMPLETED`
   - Materialize or validate completed `order_status_event` rows from that contract, or exclude unsupported rows from delivered sales.
   - Do not synthesize completion from `sales_fact_v2` alone.

3. Return/QC:
   - Implement quarantine/active-zero handling so positive `RETURN` or `RESTOCK` ledger effects do not enter active sellable stock before `return_qc_event.accepted_active_qty` exists.
   - Add tests proving returned units stay quarantine/active-zero and only QC-accepted quantity becomes active sellable.

4. Negative ledger:
   - Materialize exact owner-approved active-zero/quarantine exceptions separately for the `2` exact rows only.
   - Produce a repair/owner queue for the `2` weak-overlap and `14` unresolved rows.
   - Do not clamp all negatives blindly.

5. Cashflow:
   - Fix the D1 cashflow translator/validator interaction exposed by Agent 29: recovered `ORDER_ENTRY` rows with blank `sku_key`/`sku_id` created `18` missing cash-in candidates after recovery.
   - Either force SKU mapping before publication, or make translator/validator idempotently cover these recovered entry rows without inventing product identity.

6. Temp proof:
   - Re-run the Agent 24/29 strict validator set on a fresh temp DB.
   - Report a before/after pass/fail matrix.

## Evidence To Consume

- lifecycle contract candidates: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/lifecycle_header_completed_contract_classification.csv`
- return/QC policy proof: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/return_qc_quarantine_policy_proof.json`
- negative ledger queue: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/negative_ledger_owner_action_queue.csv`
- cashflow follow-up queue: `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_29_evidence/cashflow_recovered_entry_followup_queue.csv`

## Required Gates

Run:

```bash
python3 -m py_compile <changed-python-files>
```

Run focused pytest for all changed tests.

Run the relevant strict validators on the fresh temp DB:

- `scripts/validate_operational_stock_integration_gates.py`
- `scripts/validate_order_cashflow_coverage.py --strict`
- `scripts/validate_cashflow_invariants.py`
- `scripts/validate_operational_stock_schema.py`
- `scripts/validate_exception_queue_db.py --strict`
- policy source/gate validators if the proof materializes C3 state.

Also run:

```bash
git status --short -- db/app.db
```

Expected: empty.

## Stoplines

- No production DB apply.
- No header-only STOREB item rows as green evidence.
- No completed lifecycle synthesis without the tested same-store header-completed contract.
- No returned stock as active sellable without QC acceptance.
- No simulate-mode snapshot as production stock truth.
- No all-negative blind clamp.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run with pass/fail;
- temp DB path;
- before/after residual counts;
- validation matrix;
- rollback note;
- explicit production apply status.
