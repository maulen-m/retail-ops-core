# Agent 20 - Stock Negative-Balance Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_20_stock_negative_balance_temp_proof_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/reconciliation/count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md`
8. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_BLOCKERS_20260613_STARTERS/RUN_CLOSEOUT.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_15_ab_internal_freshness_writer_closeout.md`
10. This starter prompt.

Role: prove the minimum safe path to clear the 15 negative stock ledger balances that block `fact_inventory_snapshot_size` rebuild for `2026-06-13`.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not clamp negatives to zero as a shortcut. OD-017 keeps clamps disabled. Use source-backed inbound/count/re-entry evidence or stop as YELLOW.
- Do not write Kaspi merchant state, Web_automation, Facebook_ads, Telegram, LaunchAgents, workbooks, pricing uploads, or customer/operator messages.
- You may create copied DBs with `sqlite3 .backup` and apply only to those copies.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent20_stock_negative_balance_temp_proof_20260613/`
- Copied DBs under that evidence folder or `exports/validation/`
- Assigned closeout.
- Focused code/test patch only if an existing stock import/snapshot script has a narrow bug that blocks copied-DB proof. Do not apply production DB writes.

Tasks:

1. Reproduce the blocker read-only:

```bash
sqlite3 -readonly db/app.db "SELECT sku_id, store_code, SUM(qty_change) AS balance FROM stock_ledger GROUP BY sku_id, store_code HAVING balance < 0 ORDER BY balance, sku_id;"
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db db/app.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
```

2. For each negative SKU/store, identify the exact missing source-backed repair candidate:

- LINE31 inbound booking from AMD-01 where applicable.
- OD-004 manual count precedence, especially 06-11 22:00 FULL_SUPERSEDE or ADDITION rows.
- Direct CRM/shared-warehouse decrement risk from AMD-03, but do not invent decrements.
- Existing `stock_anchor`, `stock_adjustment_batch`, `manual_stock_counts`, `RESTORED_CANCEL_RETURN_NO_ORDER_LINK`, and inbound scripts.

3. Create copied DB:

```bash
sqlite3 db/app.db ".backup 'exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db'"
```

4. On copied DB only, test the minimal source-backed repair sequence. Preferred order mirrors the plan: inbound booking, owner-approved count/re-entry adjustments, snapshot rebuild. Do not run `clamp_negative_ledger.py` except as read-only evidence of what must not be used.
5. If existing scripts can apply to copied DB with env gates, use copied-DB apply only. If no governed script exists for a required source-backed adjustment, stop YELLOW and specify the missing script/contract.
6. Validate on copied DB:

```bash
sqlite3 -readonly exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db 'PRAGMA integrity_check;'
sqlite3 -readonly exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db "SELECT COUNT(*) FROM (SELECT sku_id, store_code, SUM(qty_change) AS balance FROM stock_ledger GROUP BY sku_id, store_code HAVING balance < 0);"
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
PYTHONPATH=. .venv/bin/python scripts/validate_inventory_cost_drift.py --db exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db --as-of 2026-06-13
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db exports/validation/agent20_stock_negative_balance_temp_proof_20260613/agent20_stock_probe.db --as-of 2026-06-13 --strict --json
```

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Exact 15 negative rows before and after on copied DB.
- For every repair row, list source evidence path, reason, event type, quantity, SKU, size/store, and whether it came from inbound, manual count supersede, manual count addition, or another accepted source.
- State whether copied-DB `fact_inventory_snapshot_size` can rebuild to `2026-06-13`.
- If `GREEN`, include exact serialized production apply proposal with backup command, env gates, expected row deltas, and rollback path. Do not run it.
- If `YELLOW`, state the missing source/contract/code gap and the smallest next action.

