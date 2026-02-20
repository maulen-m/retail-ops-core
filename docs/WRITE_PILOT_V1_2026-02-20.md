# WRITE_PILOT_V1_2026-02-20

## Goal
Pilot one representative write-capable script and prove fail-closed gating behavior without running any live apply action.

## Pilot Scope
- Script: `scripts/sync_po_parts_from_inbound_calendar.py`
- Manifest entry:
  - `env_gate: ENABLE_PO_PART_SYNC_WRITE`
  - `apply_flag: --apply`

## Contract Under Test
1. Default run is dry-run (non-mutating).
2. `--apply` without env gate must fail.
3. Env gate without `--apply` must still not write.
4. Manifest validator must pass and include the script.

## Evidence
- `exports/validation/ops_rollout_v2_9_execution_2026-02-20/p4_write_pilot/write_guard_matrix.md`

## Result
- PASS: write-side pilot checks are green in non-apply validation mode.
- No DB write/apply actions executed in this pilot phase.

## Rollback
- Docs-only rollback:
  - `git revert <commit_sha_containing_write_pilot_doc>`
- If future implementation adds code for this pilot, rollback must include:
  - per-commit revert in reverse order,
  - rerun `validate_write_side_gating.py` and strict validation chain.
