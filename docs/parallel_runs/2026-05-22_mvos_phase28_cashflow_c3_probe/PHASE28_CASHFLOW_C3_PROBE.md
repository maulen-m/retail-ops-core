# PHASE28_CASHFLOW_C3_PROBE

Status: `YELLOW_CASH_BALANCES_ROUTE_FOUND_REGISTRY_NOT_CLEARED`
Created: `2026-05-22`

This probe is copied-temp/evidence-only. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, external writes, WebUI/API mutations, ad-platform writes, cash movement, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Boundary

- Source DB: Phase27 copied DB.
- Probe DB: `exports/validation/mvos_phase28_cashflow_c3_probe/20260522_agent12_followup/app_phase28_cashflow_probe.sqlite`
- Evidence root: `exports/validation/mvos_phase28_cashflow_c3_probe/20260522_agent12_followup`
- Protected production DB SHA stayed `726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`.
- Protected workbook/source-pointer/config surfaces were not changed.

## Findings

1. Existing copied-temp cashflow rebuild can safely extend `fact_cashflow_daily` from `2026-05-04` to `2026-05-22` on a DB copy.
2. The same rebuild generated `0` new system events, so `fact_cashflow_events` still stops at `2026-05-04`.
3. Cashflow invariants still pass after the copied-temp daily rebuild: `PASS: 866 days validated`.
4. Order cashflow coverage still passes for `2026-05-22`.
5. Strict C3 source freshness remains blocked after the rebuild: `src_bank_manual_ingest` is still stale, plus the already retained ads/source/stock blockers.
6. The current inbound workbook contains a usable `Cash_Balances` source packet with `as_of: 2026-05-16 15:18:00 GMT+5`.
7. The generated evidence-only bank snapshot totals `9,323,700 KZT` equivalent, with the owner-confirmed `1,500,000 KZT` reserve still treated as non-spendable buffer, not as free operating cash.
8. The active copied DB C3 registry still points `src_bank_manual_ingest` to `~/Docs/Autonomous_business/config/bank_accounts_manual_ingest_3.5.2026.yaml`, so the validator correctly remains `YELLOW`.

## Evidence

- `cashflow_table_bounds_after_rebuild.tsv`: `fact_cashflow_daily` max `2026-05-22`; `fact_cashflow_events` max `2026-05-04`.
- `validate_cashflow_invariants_after_rebuild.txt`: pass.
- `validate_order_cashflow_coverage_20260522_after_rebuild.json`: pass.
- `validate_policy_source_freshness_20260522_after_rebuild.json`: blocked.
- `validate_policy_gate_results_strict_after_rebuild.json`: `ads_source_truth`, `cashflow_source_truth`, `source_freshness`, and `stock_source_truth` blocked.
- `cash_balances_packet/bank_accounts.yaml`: evidence-only snapshot generated from workbook `Cash_Balances`.
- `cash_balances_packet/bank_accounts_history_totals.md`: totals for the generated evidence-only snapshot.
- `cash_balances_packet/operational_decision_policy.cash_balances_packet.yaml`: evidence-only copied policy route, not production authority.

## Route Decision

This probe does not make cashflow green. It creates a precise next reviewed route:

- Accept the workbook `Cash_Balances` route as the current manual-bank source, or keep `src_bank_manual_ingest` stale.
- If accepted later, run a backup-first source-pointer/config lane or a reviewed copied-temp registry route. Do not silently update source pointers during proof work.
- Keep `cashflow_source_truth` blocked until the reviewed source route and strict validators pass.

## Exact Next Ask For CodeCaptain

Review whether the evidence-only `Cash_Balances` packet generated from `Inbound_calendar_V10.002.xlsx` may replace the stale May 3 manual bank YAML as the accepted `src_bank_manual_ingest` source route, and whether cashflow daily rebuild may be accepted as copied-temp closure for `fact_cashflow_daily` while `fact_cashflow_events` remains event-source-stale.
