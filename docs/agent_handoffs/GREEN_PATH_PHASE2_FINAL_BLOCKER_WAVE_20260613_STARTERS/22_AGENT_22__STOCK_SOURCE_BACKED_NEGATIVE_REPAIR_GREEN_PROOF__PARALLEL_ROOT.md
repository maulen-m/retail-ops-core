# Agent 22 - Stock Source-Backed Negative Repair Green Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_22_stock_source_backed_negative_repair_green_proof_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_CASHFLOW_PROD_APPLY_20260613.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_20_stock_negative_balance_temp_proof_closeout.md`
7. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
8. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md`
9. This starter prompt.

Role: produce the minimum source-backed green path for the 15 negative stock ledger balances that block `fact_inventory_snapshot_size` rebuild through 2026-06-13.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not use `clamp_negative_ledger.py` as the repair. OD-017 keeps clamps disabled.
- Do not invent stock. Every repair row needs an inbound/count/re-entry/alias/parent-child source with an evidence path.
- Do not write Kaspi merchant state, Web_automation, Facebook_ads, Telegram, LaunchAgents, workbooks, pricing uploads, customer messages, or operator messages.
- You may create copied DBs using SQLite online backup and apply only to those copies.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/`
- Copied DBs under that evidence folder.
- Assigned closeout.
- A focused code/test patch only if an existing stock import/snapshot script lacks a narrow source-backed path needed for the copied-DB proof. If patching code, keep it lane-local and say exactly which tests prove it.

Known Agent 20 negative rows:

| sku_id | balance |
| --- | ---: |
| `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_46` | -5 |
| `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_M` | -4 |
| `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_48` | -3 |
| `SUIT-31-LS_3XL` | -3 |
| `LINE-31-TS_3XL` | -2 |
| `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_S` | -2 |
| `SUIT-31-LS_XL` | -2 |
| `LINE-31-LS_XL` | -1 |
| `LINE-31-TS_XL` | -1 |
| `CL_NEW-CLO_KIDS_KID-31_BLACK_L` | -1 |
| `CL_NEW-CLO_KIDS_KID-31_BLACK_M` | -1 |
| `CL_NEW-CLO_KIDS_KID-31_BLACK_S` | -1 |
| `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_50` | -1 |
| `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_52` | -1 |
| `SUIT-31-TS_XL` | -1 |

Agent 20 candidate matrix:

`~/Docs/Autonomous_business/exports/validation/agent20_stock_negative_balance_temp_proof_20260613/analysis/repair_candidate_matrix.csv`

Tasks:

1. Reproduce the stock blocker read-only on production:

```bash
sqlite3 -readonly db/app.db "SELECT sku_id, store_code, SUM(qty_change) AS balance FROM stock_ledger GROUP BY sku_id, store_code HAVING balance < 0 ORDER BY balance, sku_id;"
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db db/app.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --strict --json
```

2. For every negative SKU, classify the source-backed repair path:

- LINE31 inbound evidence from `po_line` or accepted inbound artifacts for `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK_*`.
- Owner manual count precedence or ADDITION rows for compact `LINE-*` and `SUIT-*` parent/child SKUs.
- Numeric-to-letter or exact count evidence for `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY_*`.
- Exact source or explicit stopline for kids `CL_NEW-CLO_KIDS_KID-31_BLACK_*`.

3. Create copied DB:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db'"
```

4. On the copied DB only, test the minimal source-backed repair. Preferred order:

- import accepted inbound/count evidence using existing scripts if possible;
- otherwise create the smallest governed repair writer on the copied DB, with an explicit evidence CSV/JSON and tests;
- rebuild `fact_inventory_snapshot_size` for 2026-06-13;
- materialize C3 source freshness and gates on the copied DB.

5. Do not use a clamp as the repair. You may run clamp dry-run only as evidence of the forbidden shortcut.

6. Validate on copied DB:

```bash
sqlite3 -readonly exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db 'PRAGMA integrity_check;'
sqlite3 -readonly exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db "SELECT COUNT(*) FROM (SELECT sku_id, store_code, SUM(qty_change) AS balance FROM stock_ledger GROUP BY sku_id, store_code HAVING balance < 0);"
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
PYTHONPATH=. .venv/bin/python scripts/validate_inventory_cost_drift.py --db exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db --as-of 2026-06-13
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/agent22_stock_probe.db --strict --json
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Exact 15 negative rows before and after on copied DB.
- For every repair row, list source evidence path, source type, reason, event type, quantity, SKU, store, date, and why it is not a clamp.
- State whether copied-DB `fact_inventory_snapshot_size` rebuilds through 2026-06-13.
- State whether `src_ab_db_stock_truth` clears on copied DB.
- If `GREEN`, include exact serialized production apply proposal with backup command, env gates, expected row deltas, validators, and rollback path. Do not run it.
- If `YELLOW`, state the missing source/contract/code gap and the smallest next action.

