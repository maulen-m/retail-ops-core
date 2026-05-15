# Agent753 RED Triage Containment

Checked at: `2026-05-10T16:18:56+0500`

Status: `AGENT753_RED_CONTAINED_LOCAL_PATCH_GREEN_REVIEW_REQUIRED`

Gate: `YELLOW_REVIEW_REQUIRED`

## Summary

Agent753 remains historically `RED` because ads validator report files were refreshed outside the assigned evidence folder under ignored `exports/validation` paths. This triage adds a local containment patch to the Option C validate-only runner so future ads validator runs must use the copied DB and must write validator outputs under the run evidence directory.

This does not mark the full Agent751/752/753 wave green. The next decision is review acceptance of this containment patch and the historical ignored report writes.

## Historical Out-Of-Bound Paths

Observed ignored report paths:

| Path | mtime local | size | sha256 |
|---|---:|---:|---|
| `exports/validation/ads_sidecar_readiness/2026-05-04/ads_sidecar_readiness_report.json` | `2026-05-10T15:54:17+0500` | `2182` | `300fdd1f3b60be49be760d3dfcc2a7812c5fded0d95dbf8c1f920a797caf269a` |
| `exports/validation/ads_sidecar_readiness/2026-05-04/ads_sidecar_readiness_report.md` | `2026-05-10T15:54:17+0500` | `867` | `3eb030af8193ae91300f28b0e768ab8966ed9aea56becc3d6e9156139c62db85` |
| `exports/validation/crm_north_star_rebuild/2026-03-05/ads_offer_universe_report.json` | `2026-05-10T15:54:21+0500` | `1952` | `d5377a41ae60c967b9c2f2000a43e4621a001d089e9a2cfd2ddcb3b2d0d096ca` |

`git check-ignore -v` classifies all three as ignored by `.gitignore:68:exports/`.

No delete, revert, production apply, scheduler mutation, workbook write, or external-system write was performed during this triage.

## Containment Patch

Patched surfaces:

- `scripts/run_option_c_validate_only.py`
- `tests/test_run_option_c_validate_only.py`

Behavior added:

- `ads_sidecar_readiness` is now part of the validate-only validator matrix with `--db <copied_db>` and `--output-root <evidence_dir>/04_validator_outputs/ads_sidecar_readiness`.
- `ads_offer_universe_coverage` is now part of the validate-only validator matrix with `--db-path <copied_db>` and `--output-dir <evidence_dir>/04_validator_outputs/ads_offer_universe`.
- Validator commands now support alternate DB target flags such as `--db-path`.
- Validators marked as requiring output containment fail closed with `BLOCKED_UNCONTAINED_VALIDATOR_OUTPUT` when no output target is present or when the output target is outside the evidence directory.

## Verification

Commands run:

```bash
pytest -q tests/test_run_option_c_validate_only.py
python3 -m py_compile scripts/run_option_c_validate_only.py
git diff --no-index --check /dev/null scripts/run_option_c_validate_only.py
git diff --no-index --check /dev/null tests/test_run_option_c_validate_only.py
shasum -a 256 db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx
sqlite3 db/app.db 'PRAGMA integrity_check;'
lsof db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx || true
```

Results:

- Focused tests: `5 passed in 0.07s`.
- Python compile: passed.
- Whitespace checks for the untracked runner/test files: passed.
- Production DB integrity: `ok`.
- Active `lsof` holders for protected DB/workbook at check time: none.

Current protected-surface observation during this triage:

| Protected surface | mtime local | size | sha256 |
|---|---:|---:|---|
| `db/app.db` | `2026-05-10T16:07:23+0500` | `254992384` | `2ef7204edb103a4013e81ae9034d7aff3ad062619fac200b5d25cd14b3c07d99` |
| `excel_ui/SALES_KSP_CRM_V3.xlsx` | `2026-05-10T16:06:52+0500` | `4817723` | `30881fa2df782cff9961b96b781033cddb7c25ced4415f8ec239989155efdd90` |

These hashes are recorded as current observation only, not as a reviewed launch boundary.

## Next Safe Move

Review this containment patch and decide whether the historical ignored `exports/validation` writes are acceptable as contained. Until that review is accepted, keep the group gate review-required and do not proceed to scheduler automation, owner-publication green, production DB/workbook mutation, or external writes.
