# Stock Snapshot Runbook

## Purpose
Keep stock snapshot truth deterministic and fail-closed for PO/cashflow operations.

## Canonical anchor
- `config/anchors/STOCK_SNAPSHOT_LATEST.xlsx`
- Anchor pointer authority: `config/anchors/README.md`

## Update flow
1. Refresh source workbook in its canonical storage.
2. Update anchor symlink as documented in `config/anchors/README.md`.
3. Verify anchor health:
   - `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`

## Required checks
- `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_single_truth_alignment.py`
- `python3 scripts/validate_params.py --strict`

## Stop-line criteria
- `STOCK_SNAPSHOT_LATEST.xlsx` missing/broken symlink.
- Anchor health stale/future skew/content lag error.
- Any strict gate failure tied to stock/inbound mismatch.

## Evidence location
- `exports/validation/board_v4_<YYYY-MM-DD>/`
- Daily drift artifacts: `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.*`

## Rollback
1. Restore prior symlink target from anchor history.
2. Re-run:
   - `python3 scripts/check_anchor_health.py --project-root <REPO_PATH>`
   - `python3 scripts/validate_params.py --strict`
