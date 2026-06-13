# Green Path Phase 2 Stock Owner-Approval Remaining Dry-Run

Gate: YELLOW

Date: 2026-06-14

## Scope

This lane prepares the final stock repair path for the 9 remaining negative `stock_ledger` rows. It does not apply production writes because the required owner approval evidence is not present yet.

No Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, operator-message, or external-system writes were performed.

## Code And Manifest

- Materializer: `scripts/materialize_governed_stock_repairs.py`
- Manifest: `config/governed_stock_owner_approval_repairs_20260614.json`
- Tests: `tests/test_materialize_governed_stock_repairs.py`

The materializer now supports approval-gated repair types:

- `owner_parent_child_allocation_delta`
- `owner_manual_stock_fact_delta`

The manifest stores required phrases, but it is not approval evidence. A separate owner evidence file must be passed with `--approval-evidence`. Evidence under `docs/agent_handoffs` is rejected so a closeout or starter prompt cannot accidentally authorize the write.

## Dry-Run Evidence

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/materialize_governed_stock_repairs.py \
  --db db/app.db \
  --manifest config/governed_stock_owner_approval_repairs_20260614.json \
  --output-root exports/validation/orchestrator_stock_owner_approval_remaining_dryrun_20260614/no_approval \
  --json
```

Result:

- `applied`: `false`
- `applied_rows`: `0`
- `repair_count`: `9`
- `candidate_event_count`: `0`
- `blocked_count`: `9`
- Required approval IDs:
  - `LINE_SUIT_PARENT_CHILD_ALLOCATION_20260613`
  - `KID31_BLACK_MANUAL_OWNER_FACT_20260613`

Dry-run output:

- `exports/validation/orchestrator_stock_owner_approval_remaining_dryrun_20260614/no_approval/governed_stock_repair_summary.json`
- `exports/validation/orchestrator_stock_owner_approval_remaining_dryrun_20260614/no_approval/governed_stock_repair_blocked.csv`

## Validation

- Focused tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_materialize_governed_stock_repairs.py`
- Result: `3 passed`
- Manifest JSON parse: passed
- DB guard: `scripts/check_no_db_tracked.sh` passed
- Daily ops paused verification: `exports/automation_control/2026-06-14/20260614_002431_verify_daily-ops`, `0/10 loaded`

Note: an earlier parallel pause verification saw a transient `db/app.db` holder from this dry-run process and returned `BLOCKED` on protected-surface quietness. The sequential rerun after the reader exited is the authoritative pause proof for this closeout.

## Next Command After Owner Evidence Exists

Dry-run first:

```bash
PYTHONPATH=. .venv/bin/python scripts/materialize_governed_stock_repairs.py \
  --db db/app.db \
  --manifest config/governed_stock_owner_approval_repairs_20260614.json \
  --approval-evidence <owner-evidence-file> \
  --output-root exports/validation/orchestrator_stock_owner_approval_remaining_dryrun_20260614/owner_approved \
  --json
```

Production apply only after dry-run is clean, daily ops are paused, and a DB backup is expected:

```bash
ENABLE_GOVERNED_STOCK_REPAIR_WRITE=1 \
ALLOW_PRODUCTION_GOVERNED_STOCK_REPAIR_WRITE=1 \
PYTHONPATH=. .venv/bin/python scripts/materialize_governed_stock_repairs.py \
  --db db/app.db \
  --manifest config/governed_stock_owner_approval_repairs_20260614.json \
  --approval-evidence <owner-evidence-file> \
  --output-root exports/validation/orchestrator_stock_owner_approval_remaining_prod_apply_20260614/apply \
  --apply \
  --json
```

After apply, rebuild the `2026-06-13` stock snapshot, replay C3 materialization, run stock/source validators, run `scripts/check_no_db_tracked.sh`, and verify daily ops are still paused.
