# April 23 Stock Re-Anchor Validator Matrix

Created: `2026-05-25`
Scope: copied-temp April 23 stock re-anchor only

## Green Rule

Only use:

`COPIED_TEMP_GREEN_PROOF_FOR_REANCHOR_SCOPE_ONLY`

when all required validators exist and pass for the claimed scope, all retained blockers are visible, and no production authority is claimed.

Otherwise use:

`YELLOW_RETAINED_BLOCKER_BOARD_PROOF`

## Current Existing Gates

These commands should run if present in the checkout. If a command is absent, record it in `VALIDATOR_EXIT_MATRIX.tsv` as an implementation blocker rather than inventing a green claim.

```bash
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
python3 scripts/validate_no_help_command_writes.py --strict
python3 scripts/validate_mvos_source_contract_registry.py --strict
python3 scripts/preflight_copied_temp_wave.py --strict
sqlite3 -readonly <copied-db> 'PRAGMA integrity_check;'
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of 2026-05-25 --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
python3 scripts/validate_order_entries_freshness.py --db <copied-db> --as-of 2026-05-25 --strict
python3 scripts/validate_day_complete.py --db <copied-db> --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_sales_truth_consumers.py --db <copied-db> --strict
python3 scripts/validate_cogs_completeness_by_month.py --db <copied-db> --start 2026-04-23 --end 2026-05-25 --strict
python3 scripts/validate_inventory_snapshot_freshness.py --db <copied-db> --strict
python3 scripts/validate_stock_ledger_to_snapshot.py --db <copied-db> --strict
python3 scripts/validate_po_dashboard_invariants.py --db <copied-db> --strict
python3 scripts/validate_po_money_gate.py --db <copied-db> --as-of 2026-05-25 --json
python3 scripts/validate_exception_queue_db.py --db <copied-db> --strict
python3 scripts/validate_owner_decision_surface.py --surface stock_order_risk --strict
python3 scripts/validate_owner_decision_surface.py --surface po_inbound_readiness --strict
pytest -q
```

## Implementation-Target Gates

These validators are required by the re-anchor proof even if they do not exist yet. A missing target validator means the lane can produce evidence, but cannot claim final copied-temp green.

```bash
python3 scripts/validate_april23_anchor_workbook_contract.py \
  --xlsx "~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx" \
  --strict --json

python3 scripts/normalize_april23_stock_anchor.py --dry-run --json
python3 scripts/validate_april23_anchor_uniqueness.py --strict --json
python3 scripts/validate_april23_anchor_risk_flags.py --strict --json
python3 scripts/validate_cogs_coverage_for_anchor.py --strict --json

python3 scripts/extract_post_anchor_depletion.py \
  --db db/app.db \
  --start 2026-04-24 \
  --end 2026-05-25 \
  --dry-run --json

python3 scripts/validate_post_anchor_source_window.py \
  --start 2026-04-24 \
  --end 2026-05-25 \
  --strict --json

python3 scripts/validate_order_sku_size_identity_coverage.py \
  --start 2026-04-24 \
  --end 2026-05-25 \
  --strict --json

python3 scripts/validate_depletion_lifecycle_resolution.py \
  --start 2026-04-24 \
  --end 2026-05-25 \
  --strict --json

python3 scripts/replay_april23_stock_anchor_copied_temp.py \
  --db <copied-db> \
  --anchor april23_anchor_normalized.csv \
  --depletion post_anchor_depletion_ranked.csv \
  --as-of 2026-05-25 \
  --dry-run --json

python3 scripts/generate_april23_reanchor_workbooks.py --dry-run --json
python3 scripts/validate_reanchor_output_workbook_contract.py --strict --json
python3 scripts/validate_reanchor_totals_reconciliation.py --strict --json
```

## Gate Table

| Gate | Purpose | Green condition | Yellow condition | Red condition |
| --- | --- | --- | --- | --- |
| DB tracked check | Prevent tracked production DB state | no tracked DB | n/a | tracked DB found |
| DB integrity | Ensure DB readable | `ok` | n/a | integrity failure |
| Write-side gating | Prevent unguarded write paths | strict pass | n/a | strict fail |
| Source registry | Validate active source contracts | strict pass | n/a | invalid JSON/schema |
| Anchor workbook contract | Prove April workbook sheets/columns | strict pass | validator missing | schema mismatch |
| Anchor uniqueness | Prevent duplicate stock rows | no duplicates | retained duplicate report | duplicate active key |
| Anchor risk flags | Preserve blocked/low/negative rows | all visible | retained warnings | hidden flags |
| Replay source window | Cover `2026-04-24..2026-05-25` | covered or retained with explicit blocker | source gaps visible | gaps hidden |
| Identity coverage | Ensure SKU/size/quantity identity | all deducted rows identity-bearing | quarantines visible | identity-missing rows deducted |
| Lifecycle resolution | Protect cancel/return behavior | all deducted/add-back rows source-backed | unresolved rows quarantined | status guessed |
| Replay idempotency | Prevent double depletion | repeated run stable | n/a | mismatched repeated run |
| Negative contradiction | Preserve negative rows | visible and scoped | retained visible blocker | hidden/clamped without audit |
| COGS completeness | No zero COGS | known and missing separated | missing rows visible | missing COGS set to zero |
| Output workbook contract | Required sheets/columns | strict pass | minor warning visible | missing required sheet |
| Totals reconciliation | Tie workbooks to CSVs | exact or explained | retained mismatch visible | unexplained mismatch |
| PO/cash/publication gates | Prevent false downstream claims | pass for claimed surface | blockers visible | claimed green with blockers |
| Regression | Protect existing code | `pytest -q` pass | unrelated known failures documented | new relevant failure |

## Stopline Labels

Use these labels in `RETAINED_BLOCKER_BOARD.md`:

- `ANCHOR_SCHEMA_MISMATCH`
- `ANCHOR_DUPLICATE_KEY`
- `BLOCKED_ANCHOR_ROW`
- `LOW_CONFIDENCE_ANCHOR_ROW`
- `NEGATIVE_REPLAY_CONTRADICTION`
- `MISSING_COGS`
- `UNMATCHED_SKU_ALIAS`
- `MISSING_SIZE`
- `SKU_SIZE_NOT_IN_ANCHOR`
- `BUNDLE_CHILD_UNRESOLVED`
- `OFFER_ONLY_AVAILABILITY_ROW`
- `LIFECYCLE_STATUS_UNRESOLVED`
- `RETURN_OR_CANCEL_NO_QC`
- `PARTIAL_CANCEL_NO_ENTRY_EVIDENCE`
- `DUPLICATE_MOVEMENT`
- `SOURCE_WINDOW_GAP`
- `POST_ANCHOR_REPLAY_SOURCE_MISSING`
