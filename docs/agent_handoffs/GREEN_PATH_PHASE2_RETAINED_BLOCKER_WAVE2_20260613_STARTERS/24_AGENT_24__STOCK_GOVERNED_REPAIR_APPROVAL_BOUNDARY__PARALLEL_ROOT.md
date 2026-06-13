# Agent 24 - Stock Governed Repair Approval Boundary

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_24_stock_governed_repair_approval_boundary_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_CASHFLOW_PROD_APPLY_20260613.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_22_stock_source_backed_negative_repair_green_proof_closeout.md`
7. This starter prompt.

Role: determine whether the remaining 15 negative `stock_ledger` balances can be repaired from existing source/owner artifacts, or produce the exact owner approval phrases needed before a governed repair writer can be implemented. Do not apply clamps or invented stock.

Hard boundary:

- Do not mutate production `db/app.db`.
- Do not edit repo files.
- Do not perform Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes.
- Do not apply `scripts/clamp_negative_ledger.py` except read-only/dry-run evidence if needed.
- You may create copied DBs and evidence files only.

Allowed writes:

- Evidence under `~/Docs/Autonomous_business/exports/validation/agent24_stock_governed_repair_approval_boundary_20260613/`
- Copied DBs under that evidence folder.
- Assigned closeout.

Tasks:

1. Reproduce the current retained stock blocker read-only:

```bash
sqlite3 -readonly db/app.db "SELECT sku_id, store_code, SUM(qty_change) AS balance FROM stock_ledger GROUP BY sku_id, store_code HAVING balance < 0 ORDER BY balance, sku_id;"
PYTHONPATH=. .venv/bin/python scripts/rebuild_snapshot.py --db db/app.db --date 2026-06-13 --store UNIVERSAL --mode ledger --compare
PYTHONPATH=. .venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
```

2. Search existing owner/source artifacts before asking for human input. Include at least:

- `~/Docs/Autonomous_business/config/owner_decisions/`
- `~/Docs/Autonomous_business/config/anchors/manual_stock_counts/`
- `~/Docs/Autonomous_business/docs/inventory/`
- `~/Docs/Autonomous_business/docs/parallel_runs/`
- `~/Docs/Autonomous_business/exports/validation/agent22_stock_source_backed_negative_repair_green_proof_20260613/`

3. For each of the 15 negative rows, classify exactly one of:

- `SOURCE_BACKED_APPLY_READY`: existing source and existing governed writer/import path are sufficient.
- `SOURCE_BACKED_NEEDS_CODE`: source exists, but a narrow writer/import path must be implemented first.
- `OWNER_APPROVAL_NEEDED`: source is plausible but needs owner approval of mapping/allocation.
- `NO_SOURCE_STOPLINE`: no exact source exists and no approval phrase can honestly replace missing evidence without declaring a manual owner fact.

4. Produce a row-level matrix with:

- `sku_id`
- `current_balance`
- `needed_qty`
- `source_type`
- `source_artifact_path`
- `source_reference`
- `proposed_event_type`
- `proposed_event_date`
- `approval_status`
- `why_not_clamp`
- `minimum_next_action`

5. If all 15 rows are already source-backed and writer-ready, create a copied DB with SQLite online backup and prove the full repair without production apply. Otherwise, do not implement partial stock repair; instead provide exact owner approval phrases that would unlock the missing rows while preserving provenance.

Closeout requirements:

- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Exact retained blockers for `src_ab_db_stock_truth`.
- Row-level 15-row matrix.
- Existing artifacts that already approve or disapprove Nike numeric-letter mapping, kids numeric/height-letter mapping, LINE31 `po_line` inbound use, and LINE/SUIT parent-to-child stock allocation.
- If owner approval is needed, provide copy-paste approval phrases grouped by decision. Each phrase must name exact SKUs, sizes, quantities, dates, and whether the approval creates a manual owner fact or authorizes a mapping contract.
- If code is needed, specify the smallest script/table/validator changes and copied-DB proof sequence. Do not write the code.

Success bias: preserve `stock_ledger` provenance. A repair row must explain the missing inbound/allocation/mapping source; it must never use `NEGATIVE_CLAMP_*` as business truth.
