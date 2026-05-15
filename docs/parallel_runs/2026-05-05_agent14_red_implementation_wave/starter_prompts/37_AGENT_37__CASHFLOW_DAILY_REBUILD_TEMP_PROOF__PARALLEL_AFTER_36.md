# Agent 37 - Cashflow Daily Rebuild Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_cashflow_daily_rebuild_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_36.md`
5. this starter prompt

## Mission

Prove whether `fact_cashflow_daily` can be rebuilt through `2026-05-04` on a copied Agent 36 temp DB without weakening any C3 gates.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- external-system writes;
- code edits unless a test-proven cashflow rebuild bug blocks the task and you can keep the patch narrow.

## Required Starting DB

Copy:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db`

to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db`

Do not mutate Agent 36's DB directly.

## Required Work

1. Verify initial DB integrity.
2. Run `scripts/rebuild_cashflow_calendar.py` on the temp DB from `2026-04-16` through `2026-05-04`, dry-run first, then `ENABLE_CASHFLOW_WRITE=1 --apply` only on the temp DB.
3. Rerun cashflow coverage, cashflow invariants, C3 source freshness, C3 policy gate results, and operational integration gates.
4. State whether `fact_cashflow_daily` freshness is cleared and whether any cashflow values look inconsistent with current manual-bank-anchor truth.
5. Preserve all remaining non-cashflow blockers fail-closed.

## Suggested Commands

```bash
mkdir -p ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/logs
cp ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_36_evidence/agent36_combined_temp_after_33_34_35_20260504.db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db 'PRAGMA integrity_check;'
python3 scripts/rebuild_cashflow_calendar.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --start-date 2026-04-16 --end-date 2026-05-04 --run-id agent37_cashflow_daily_rebuild_dry_run
ENABLE_CASHFLOW_WRITE=1 python3 scripts/rebuild_cashflow_calendar.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --start-date 2026-04-16 --end-date 2026-05-04 --run-id agent37_cashflow_daily_rebuild_apply --apply
```

## Required Gates

Run and record:

```bash
python3 scripts/validate_order_cashflow_coverage.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --as-of 2026-05-04 --strict --json
python3 scripts/validate_cashflow_invariants.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db
python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --as-of 2026-05-04 --strict --json
python3 scripts/validate_policy_gate_results.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --strict --json
python3 scripts/validate_operational_stock_integration_gates.py --db ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db --as-of 2026-05-04 --json
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_37_evidence/agent37_cashflow_daily_rebuild_temp_20260504.db 'PRAGMA integrity_check;'
git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
```

## Expected Gate

`GREEN` only if cashflow daily freshness clears and all cashflow gates pass on the temp DB with protected production surfaces untouched.

`YELLOW` is correct if cashflow is improved but publication still blocks on non-cashflow residuals.

`RED` if the rebuild corrupts cashflow, breaks invariants, mutates production, or hides stale data.
