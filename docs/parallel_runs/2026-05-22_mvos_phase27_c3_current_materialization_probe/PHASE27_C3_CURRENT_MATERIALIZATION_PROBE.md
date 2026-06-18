# Phase 27 C3 Current Materialization Probe

Gate: `YELLOW`

Created: `2026-05-22T04:14:24+0500`
Verified: `2026-05-22T04:18:15+0500`

This lane added a source-filtered C3 materialization path and ran a copied-DB
probe for current as-of `2026-05-22`. It does not authorize production DB
writes, workbook writes, source-pointer writes, scheduler changes, WebUI/API
mutations, external writes, ad-platform writes, cash movement, PO commitment,
stock changes, price changes, owner publication, production preflight, or
production apply.

## Why This Lane Exists

The Phase24 C3 snapshot showed `8` missing requested-as-of freshness rows and
`6` blocked policy gates. A broad `materialize_c3_policy_state.py` dry-run was
too slow for the fast blocker-closure loop because it walked broad external
evidence roots. The efficient repair was to make source-freshness
materialization source-selectable, then probe the exact lightweight/current
rows on a copied DB only.

## Code/Test Change

Added repeated `--source-id` filtering to:

- `scripts/materialize_policy_source_freshness.py`
- `scripts/materialize_c3_policy_state.py`
- `core/ops/policy_materialization_c3.py`

The default behavior remains unchanged when no `--source-id` is provided.

Focused test added:

- `tests/test_policy_materialization_c3.py::test_source_freshness_materializer_can_filter_source_ids`

## Copied DB Evidence

Evidence root:

`exports/validation/mvos_phase27_c3_current_materialization_probe/20260522_0405`

Copied DB:

`exports/validation/mvos_phase27_c3_current_materialization_probe/20260522_0405/app_phase27_c3_probe.sqlite`

Initial production/copy SHA matched:

`726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`

Source rows materialized on copied DB only:

| source_id | status | blocks_publication | max_observed_at | result |
| --- | --- | ---: | --- | --- |
| `src_ab_db_operational_truth` | `BLOCKED` | `1` | `2026-05-14T23:59:59+05:00` | retained; all `9` operational tables stale |
| `src_bank_manual_ingest` | `STALE` | `1` | `2026-05-03T23:11:50+05:00` | retained; no parse issues, but stale |
| `src_facebook_ads_external_ads` | `STALE` | `1` | `2026-05-04T23:59:59+05:00` | retained |
| `src_inbound_workbook` | `FRESH` | `0` | `2026-05-16T15:28:59+05:00` | copied-temp current row closed |
| `src_payment_evidence_root` | `FRESH` | `0` | `2026-05-20T23:44:09+05:00` | copied-temp current row closed |
| `src_web_automation_kaspi_marketing_directapi` | `BLOCKED` | `1` | `2026-05-04T23:59:59+05:00` | retained; packet as-of/coverage remains May4 |

The broad external roots `src_ecommerce_po_artifacts` and
`src_sourcing_research_supplier_routes` were intentionally not scanned as proof
in this lane; they remain missing until a bounded manifest/source packet exists.

## Validator Delta

Before Phase27 copied-temp materialization:

- `validate_policy_source_freshness.py --as-of 2026-05-22 --strict --json`:
  `8` errors.
- `validate_policy_gate_results.py --strict --json`: `6` errors.

After Phase27 filtered copied-temp materialization and gate materialization:

- `validate_policy_source_freshness.py --as-of 2026-05-22 --strict --json`:
  `6` errors.
- `validate_policy_gate_results.py --strict --json`: `4` errors.
- `exception_queue` and `po_source_truth` now pass on the copied DB.
- `ads_source_truth`, `cashflow_source_truth`, `source_freshness`, and
  `stock_source_truth` remain blocked.

## Retained Blockers

- `src_ab_db_operational_truth`: blocked/stale rollup; current registry still
  treats it as publication-blocking.
- `src_bank_manual_ingest`: stale manual bank/cash source.
- `src_facebook_ads_external_ads`: stale Meta/Facebook source.
- `src_web_automation_kaspi_marketing_directapi`: accepted packet exists but is
  May4 coverage, not May22 coverage.
- `src_ecommerce_po_artifacts` and `src_sourcing_research_supplier_routes`:
  missing current-as-of rows because broad external-root scans are not accepted
  as fast proof here.
- Physical stock truth remains retained because the owner confirmed no fresher
  physical stock source exists.

## Decision

This lane is `YELLOW`, not green. It reduces the C3 blocker and hardens the
tooling needed for exact next probes, but copied-temp validators still fail.

## Verification

- `pytest -q tests/test_policy_materialization_c3.py`: PASS,
  `26 passed in 127.29s`.
- `bash scripts/lint_docs.sh`: PASS.
- `python3 scripts/validate_mvos_source_contract_registry.py --strict`: PASS,
  `contract_count=19`, `active_contract_count=17`, `warning_count=43`.
- `bash scripts/check_no_db_tracked.sh`: PASS, no tracked/staged DB files.
- `git diff --check -- core/ops/policy_materialization_c3.py
  scripts/materialize_policy_source_freshness.py
  scripts/materialize_c3_policy_state.py tests/test_policy_materialization_c3.py
  docs/current/CURRENT_BLOCKER_BOARD.tsv
  docs/current/CURRENT_SOURCE_TRUTH_MAP.md
  docs/parallel_runs/2026-05-22_mvos_phase27_c3_current_materialization_probe/PHASE27_C3_CURRENT_MATERIALIZATION_PROBE.md`:
  PASS.
- `CURRENT_BLOCKER_BOARD.tsv` sanity: PASS, `20` rows and `8` columns.
- Copied DB `PRAGMA integrity_check`: PASS, `ok`.
- Production `db/app.db` SHA remained
  `726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`;
  copied DB changed only inside the Phase27 evidence folder.
- Expected retained-stop validators on copied DB:
  `validate_policy_source_freshness.py --as-of 2026-05-22 --strict --json`
  exits non-zero with `6` errors; `validate_policy_gate_results.py --strict
  --json` exits non-zero with `4` errors.
