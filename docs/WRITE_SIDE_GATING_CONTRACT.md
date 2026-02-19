# WRITE_SIDE_GATING_CONTRACT

## Purpose
Define one fail-closed contract for write-capable scripts so writes cannot happen accidentally.

## Contract (non-negotiable)
1. Default mode is dry-run / read-only.
2. Any write path requires both:
   - explicit environment gate (`ENABLE_* = 1`), and
   - explicit CLI write flag (`--apply`).
3. Missing either condition must produce a non-zero exit.
4. If a script mutates DB/external state, the gate check must run before the first write operation.
5. Coverage source of truth is `config/write_side_gating_manifest.yaml`.
6. Contract enforcement is automated by `scripts/validate_write_side_gating.py`.

## Canonical gated scripts
- See `config/write_side_gating_manifest.yaml` for the authoritative list and required gates.
- Additions must update the manifest and pass validator checks before merge.

## Validation
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_write_side_gating_contract.py`
- `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml`
- `python3 scripts/validate_params.py --strict`

## Rollback
- `git revert <commit_sha>`
- Re-run the two validation commands above.
