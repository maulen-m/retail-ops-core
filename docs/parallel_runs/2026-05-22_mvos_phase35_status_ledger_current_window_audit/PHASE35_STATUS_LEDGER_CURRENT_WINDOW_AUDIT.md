# PHASE35_STATUS_LEDGER_CURRENT_WINDOW_AUDIT

Status: `YELLOW_RETAINED_CURRENT_WINDOW`
Created: `2026-05-22`
Evidence root: `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313`

This audit is read-only/evidence-only. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, WebUI/API/Kaspi mutations, Web_automation writes, external writes, ad-platform writes, cash movement, supplier payment, PO commitment, stock or price changes, owner publication, production preflight, or production apply.

## Decision

`R012` / `src_ab_db_order_status_truth` remains `YELLOW`.

The best local status-ledger proof is still the accepted scoped `STOREB` / `ACMEWEAR` / `UNIVERSAL` ledger through `2026-05-17`. It is valid and provenance-backed for that window, but it does not cover `2026-05-18`. No exact local WebUI ArchiveOrders source file was found that can extend the trusted window to `2026-05-18` without a new source acquisition or a reviewed contract change.

## Validator Matrix

| Input | Window | Store scope | Exit | Result |
| --- | --- | --- | ---: | --- |
| Agent878 scoped copied ledger | `2026-05-05..2026-05-17` | `STOREB`, `ACMEWEAR`, `UNIVERSAL` | `0` | `PASS`: `ledger_rows=1174`, `gap_count=0`, `pack_window_provenance_error_count=0` |
| Agent878 scoped copied ledger | `2026-05-05..2026-05-18` | `STOREB`, `ACMEWEAR`, `UNIVERSAL` | `1` | `FAIL`: `ledger_rows=1174`, `gap_count=3`, `pack_window_provenance_error_count=0` |
| Default full-parse copied ledger | `2026-05-05..2026-05-18` | `11KZ`, `MELVIS`, `STOREB`, `ACMEWEAR`, `UNIVERSAL` | `1` | `FAIL`: `ledger_rows=20607`, `gap_count=5`, `pack_window_provenance_error_count=80` |

## Exact Gaps

Scoped `2026-05-18` failure:

| store_code | gap_start | gap_end | reason |
| --- | --- | --- | --- |
| `STOREB` | `2026-05-18` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `ACMEWEAR` | `2026-05-18` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `UNIVERSAL` | `2026-05-18` | `2026-05-18` | `UNION_WINDOW_GAP` |

Default five-store failure:

| store_code | gap_start | gap_end | reason |
| --- | --- | --- | --- |
| `11KZ` | `2026-05-05` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `MELVIS` | `2026-05-05` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `STOREB` | `2026-05-05` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `ACMEWEAR` | `2026-05-05` | `2026-05-18` | `UNION_WINDOW_GAP` |
| `UNIVERSAL` | `2026-05-05` | `2026-05-18` | `UNION_WINDOW_GAP` |

## Source Inventory

Local evidence search found only these current manual import batches:

- `imports/webui_archive_manual/17.05.2026_09_54_42`: `STOREB`, `ACMEWEAR`, `UNIVERSAL`
- `imports/webui_archive_manual/17.05.2026_18_26_58`: `STOREB`, `ACMEWEAR`, `UNIVERSAL`
- `~/Downloads/ActiveOrders/archive_orders/17.05.2026_09_54_42`: duplicate hash matches for the morning import
- `~/Downloads/ActiveOrders/archive_orders/<store>`: older May 14 local downloads for `STOREB`, `ACMEWEAR`, `UNIVERSAL`

No local `ArchiveOrders` source artifact was found for `2026-05-18`; no same-window `11KZ` or `MELVIS` evidence was found for the May proving window. Full inventory with hashes is at:

`exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/source_inventory/archiveorders_local_inventory.csv`

## Evidence Files

- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/ledger_copies/agent878_scoped_20260517_pass/continuity_report.json`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/ledger_copies/agent878_scoped_20260518_fail/continuity_report.json`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/ledger_copies/default_full_parse_copy/continuity_report.json`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/ledger_copies/agent878_scoped_20260518_fail/continuity_gaps.csv`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/ledger_copies/default_full_parse_copy/continuity_gaps.csv`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/commands/validate_scoped_20260517_pass.stdout.txt`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/commands/validate_scoped_20260518_fail.stdout.txt`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/commands/validate_default_5store_20260518.stdout.txt`
- `exports/validation/mvos_phase35_status_ledger_current_window_audit/20260522_054313/protected_surface_sha256_start.tsv`

## Why This Is Still Useful

Phase35 narrows the blocker to a precise truth boundary:

- The validator is not broken; it passes the exact proven `2026-05-05..2026-05-17` scoped ledger.
- The current `2026-05-18` failure is not caused by missing provenance in the scoped ledger; it is a real one-day window gap.
- The default five-store route is worse and should not be used for green claims because it still has stale full-parse windows and missing provenance.

## Next Safe Route

1. If the final proof must cover `2026-05-18`, acquire exact read-only WebUI ArchiveOrders source for the required stores through `2026-05-18`, then rebuild and validate the ledger.
2. If no fresher source exists, ask CodeCaptain whether a scoped/dated status-ledger contract can keep `2026-05-18` retained without blocking unrelated copied-temp closures.
3. Do not production-apply the day-complete copied-temp patch or owner-publication path until CodeCaptain accepts the route and a later explicit write lane is authorized.
