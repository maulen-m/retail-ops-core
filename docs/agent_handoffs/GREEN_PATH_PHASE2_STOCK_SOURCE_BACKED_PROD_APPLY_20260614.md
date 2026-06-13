# Green Path Phase 2 Stock Source-Backed Production Apply

Gate: YELLOW. The source-backed LINE31 and Nike rows are repaired in production; stock remains blocked by 9 owner/source-stopline rows.

Date: 2026-06-14

## Scope

This lane added a governed, env-gated stock repair materializer for source-backed negative balances only. It intentionally did not apply LINE/SUIT parent-child allocation rows or KID-31 S/M/L manual facts because those require exact owner approval or a new exact source.

No Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, operator-message, or external-system writes were performed.

## Code And Manifest

- Manifest: `config/governed_stock_repair_events_20260613.json`
- Materializer: `scripts/materialize_governed_stock_repairs.py`
- Tests: `tests/test_materialize_governed_stock_repairs.py`

The materializer is dry-run by default. Apply requires:

- `ENABLE_GOVERNED_STOCK_REPAIR_WRITE=1`
- `ALLOW_PRODUCTION_GOVERNED_STOCK_REPAIR_WRITE=1` for `db/app.db`

## Production Write

- Evidence root: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/`
- Pre-write backup: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/backups/app_before_stock_source_backed_repair_prod_apply_20260614.db`
- Materializer backup: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/apply/backups/app_2026-06-14_000552.db`
- C3 backup: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/c3_backups/app_before_agent8_c3_policy_materialization_20260614_000640.db`
- Applied rows: `6`
- Blocked rows in manifest: `0`

Inserted source-backed rows:

- `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46`: `+5`, `MANUAL_COUNT_SIZE_ALIAS`
- `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_48`: `+3`, `MANUAL_COUNT_SIZE_ALIAS`
- `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_50`: `+1`, `MANUAL_COUNT_SIZE_ALIAS`
- `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_52`: `+1`, `MANUAL_COUNT_SIZE_ALIAS`
- `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M`: `+4`, `PO_INBOUND_LINE`, `reference_id=907`
- `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_S`: `+2`, `PO_INBOUND_LINE`, `reference_id=906`

These deltas are limited to the current negative balances. The LINE31 PO lines arrived before an April physical anchor, so the repair does not insert the full historical PO receipt and does not double-count stock already represented by the anchor.

## Validation

- Focused tests: `6 passed`
- Production dry-run before apply: `candidate_event_count=6`, `blocked_count=0`
- Copied DB apply: `applied_rows=6`, integrity `ok`
- Production integrity after apply: `ok`
- DB guard: passed
- Daily ops paused after write: `exports/automation_control/2026-06-14/20260614_000908_verify_daily-ops`, `0/10 loaded`
- C3 run id: `orchestrator_stock_source_backed_repair_prod_apply_20260614`
- C3 gate shape: `PASS=7`, `BLOCKED=2`
- `ads_source_truth`: `PASS`
- `stock_source_truth`: `BLOCKED`
- Strict source freshness: fails only `src_ab_db_stock_truth STALE`

Snapshot rebuild still correctly refuses:

```text
9 negative ledger balances detected.
```

Remaining negative rows:

```text
SUIT-31-LS_3XL|UNIVERSAL|-3
LINE-31-TS_3XL|UNIVERSAL|-2
SUIT-31-LS_XL|UNIVERSAL|-2
LINE-31-LS_XL|UNIVERSAL|-1
LINE-31-TS_XL|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_L|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_M|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_S|UNIVERSAL|-1
SUIT-31-TS_XL|UNIVERSAL|-1
```

## Approval Phrases Needed

LINE/SUIT parent-child allocation:

```text
I approve a governed stock allocation contract from the approved parent physical stock pools to these compact child stock_ledger rows, effective 2026-06-11T22:00:00+05:00, using the 2026-06-04 approved manual stock count plus the 2026-06-11 owner-authoritative ADDITION batch and the existing compact child article-map evidence as source artifacts. Allocate exactly: SUIT-31-LS_3XL +3 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL; SUIT-31-LS_XL +2 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL; SUIT-31-TS_XL +1 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL; LINE-31-LS_XL +1 from CL_OC_MEN_LINE51_WHITE_XL; LINE-31-TS_XL +1 from CL_OC_MEN_LINE51_WHITE_XL; LINE-31-TS_3XL +2 from CL_OC_MEN_LINE51_WHITE_3XL. This authorizes a mapping/allocation contract, not invented stock and not a NEGATIVE_CLAMP_* repair. It does not authorize Kaspi merchant, pricing, workbook, Telegram, LaunchAgent, customer, or operator-message writes.
```

KID-31 black manual owner fact:

```text
I create a manual owner stock fact for KID-31 black letter rows because no exact source artifact currently proves the S/M/L allocation. Effective 2026-06-04T14:00:23+05:00, add exactly CL_NEW-CLO_KIDS_KID-31_BLACK_L +1, CL_NEW-CLO_KIDS_KID-31_BLACK_M +1, and CL_NEW-CLO_KIDS_KID-31_BLACK_S +1 to the UNIVERSAL stock ledger as owner-approved manual facts. This approval does not claim these rows came from the numeric/height 22/24/26/28/30 count unless a separate mapping contract is approved. This is not a NEGATIVE_CLAMP_* repair and does not authorize external writes.
```

## Rollback

Use the pre-write backup if this source-backed stock repair must be reverted:

```bash
sqlite3 db/app.db ".restore 'exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/backups/app_before_stock_source_backed_repair_prod_apply_20260614.db'"
```

After rollback, rerun C3 policy materialization and the stock negative-balance query before any owner-facing publication.
