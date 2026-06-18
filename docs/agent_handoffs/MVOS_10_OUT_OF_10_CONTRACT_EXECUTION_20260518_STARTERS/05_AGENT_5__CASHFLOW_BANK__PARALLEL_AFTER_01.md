# Agent 5: Cashflow, Bank, Payment, And COGS Gate Proof

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`
4. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
5. `~/Docs/Autonomous_business/docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`
6. `~/Docs/Autonomous_business/config/bank_accounts.yaml`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent1_scope_registry_boundary_closeout.md`
9. this assigned starter prompt

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent5_cashflow_bank_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos-10-out-of-10-contract-execution/agent5_cashflow_bank_evidence`

## Task

Build read-only or copied-temp evidence for the Cashflow And Bank Gate.

Preserve:

- actual vs modelled cash separation;
- statement/account source dates;
- reserve and buffer classification separate from spendable operating cash;
- no missing costs treated as zero.

Produce:

- `CASH_RISK_DAILY_TRUST_BANNER.json`
- `CASHFLOW_SOURCE_TRUTH_MATRIX.tsv`
- `MISSING_COGS_BLOCKER_MATRIX.tsv`
- `PAYMENT_EVIDENCE_ROOT_STATUS.json`
- `BANK_BALANCE_SNAPSHOT_EVIDENCE.tsv`

Run where safe:

```bash
python3 scripts/validate_cashflow_invariants.py
python3 scripts/validate_cashflow_actual_model_separation.py --strict
python3 scripts/validate_order_cashflow_coverage.py --strict
python3 scripts/validate_monthly_cash_reconciliation.py --strict
```

## Boundary

Read-only or copied-temp only. Do not mutate bank data, workbook, production DB, cashflow source pointers, payment records, external accounts, owner publication, cash, PO, stock, price, or schedulers.

## Gate Guidance

Use `Gate: GREEN` only if cash source, payment source, bank balance source, reserve treatment, and COGS coverage pass for declared scope.

Use `Gate: YELLOW` if manual cash, bank, payment evidence, COGS, or trust-banner blockers remain.

Use `Gate: RED` if actual/modelled cash is mixed, stale cash is presented as current, or any cash movement/action is implied.
