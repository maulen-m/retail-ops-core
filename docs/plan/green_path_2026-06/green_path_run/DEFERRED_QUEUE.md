# DEFERRED_QUEUE

Parked items at the Phase-1/2 handoff. NONE are blocking — each has a fallback applied and a clear unblock. The 9 parked scheduler jobs are blocked on business-DATA that Phase 2 restores (they are NOT infra-broken); they will pass on their own once their data gate clears.

| item | lane | kzt_exposure | age_days | fallback_applied | resurfaces_at / unblock |
|---|---|---|---|---|---|
| job: kaspi-daily-ops-report (rc1 shipment_preflight) | WS-OPS/WS-STOCK | n/a | 0 | parked; not infra | clears when shipment/stock truth restored (Phase 2) |
| job: single-truth-preflight (rc1 on_delivery_freeze + workbook anchor) | WS-STOCK/WS-CASH | n/a | 0 | parked | clears when on_delivery_freeze lifted + workbook anchor reconciled (Phase 2) |
| job: operational-stock-daily-truth (RED_BLOCKED, 2309 exceptions) | WS-STOCK | n/a | 0 | parked | clears when stock truth + quarantine drained (Phase 2) |
| job: end-of-day (rc1 on_delivery_freeze + transfer freshness) | WS-PROFIT/WS-CASH | ~225k/day blind revenue | 0 | EOD apply pre-authorized (OD-015) but blocked on data | first supervised apply once entries+COGS+freeze clear (Phase 2) |
| job: on-delivery-residuals (exits 3 by design, 120 residuals) | WS-RESID | 425,015.24 | 0 | residual settlement apply pre-authorized (OD-015) | Phase-2 residual lane (scoped 120-order set) |
| job: exchange-import (Binance C2C API-key/stale sync) | WS-CASH | n/a | 0 | parked | needs exchanger sync / key check — Phase-2 cash lane or owner if key dead (STOP-THE-LINE only if blocks >50%) |
| job: kaspi-marketing-ads (rc78, stale/no current log) | WS-ADS | n/a | 0 | parked | Phase-2 ads-truth lane diagnoses live |
| job: external-database-backup (Drive perms, rc78) | n/a | n/a | 0 | SUPERSEDED by com.example.green-path-offsite-backup | owner-review at acceptance (keep or remove) |
| job: table-delta-backup (drive deadlock, rc2) | n/a | n/a | 0 | SUPERSEDED-pending-review | owner-review at acceptance |
| OCR residual cells (LINE51 S=82, kids 140/28=32 vs33, 150/30=28 vs29, line52 2XL=20, rombik 3XL not-captured) | WS-STOCK | low | 0 | consensus value taken; ledger reconciliation catches ±1 residue | passive owner glance at acceptance |
| family-mapping flags F-1/F-2/F-3 (logotype 3-in-1 vs 06-04 set; RUSH; T-SHIRT) | WS-STOCK | n/a | 0 | resolve at dim_sku import time, not OCR's call | Phase-2 count-import lane |
| leftover external-volume probe files (.codex_mkdir_test_*, .codex_write_test_*) | housekeeping | 0 | 0 | harmless | delete at any convenient point |
| new colors Bean Paste/Pomelo/Eggplant(+Iris) | WS-STOREFRONT | idle inventory | 0 | gated, owner-triggered | owner sends assets ~2026-06-18 → ingest |
| 2794142 campaign (June CRR 82.8%) | WS-ADS | ad waste | 0 | OD-019 rule auto-pauses once ads truth restores | Phase-2 ads lane (or optional owner cabinet pause now) |
