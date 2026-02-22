# PO Money Gate Contract

## Purpose
Block PO publication when capital-critical truth checks are red. This gate is fail-closed by default.

## Required checks
The following checks are blocking:
- `scripts/check_anchor_health.py`
- `scripts/validate_inbound_sheet_consistency.py`
- `scripts/validate_single_truth_system.py`
- `scripts/validate_cogs_integrity.py`
- `scripts/validate_single_truth_alignment.py`
- `scripts/validate_po_money_gate.py`

Optional check (blocking only when enabled):
- `scripts/validate_offer_linkage.py` with `--require-offer-linkage-strict`

## Execution
Default execution:

```bash
python3 scripts/validate_po_money_gate.py --json
```

Strict offer-linkage execution:

```bash
python3 scripts/validate_po_money_gate.py --require-offer-linkage-strict --json
```

## Fail-Closed Rules
- Missing inbound workbook anchor is a hard fail.
- Any required check with non-zero exit code is a hard fail.
- Optional checks must never be counted as pass silently; they are reported in `optional_failed`.

## Output Contract
`validate_po_money_gate.py --json` returns:
- `ok` (`bool`)
- `required_failed` (`list[str]`)
- `optional_failed` (`list[str]`)
- `checks` (`list` of per-check details including command, exit code, stdout/stderr)
- `inbound_workbook`, `db_path`, `project_root`

## Rollback
If this gate causes regressions:
1. Revert the gate integration commit.
2. Re-run:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_validate_po_money_gate.py tests/test_po_money_gate_contract.py`
3. Restore previous PO publication flow only after strict chain is green.
