# MVOS 10/10 Decision-Grade Acceptance Contract

Status: `DRAFT_FOR_CODECAPTAIN_REVIEW`

Created: `2026-05-18`

Scope: `Autonomous_business` Kaspi operating system, including source truth, MVOS proof, production apply safety, daily business operations, and owner-publication readiness.

This document is not yet the canonical final contract. It becomes canonical only after CodeCaptain review and explicit human-owner approval.

## Purpose

Define what a fully functioning `10/10` Autonomous_business system means in practical, verifiable terms.

This contract is designed for agents to execute against. A future implementation agent should be able to read this document, identify the next failing gate, produce evidence, and stop safely without guessing.

## Plain-English Definition

The project is `10/10` when the repo can reliably run the business decision loop end to end:

1. Fresh source truth is available for orders, sales, ads, cash, stock, PO/inbound, and lifecycle/status.
2. The system turns that truth into decision-grade economics, PO readiness, exception handling, daily ops outputs, and owner-facing summaries.
3. All required validators pass on a copied-temp proof and then on the protected production boundary after an explicitly approved apply.
4. Daily business automations can be paused, resumed, and verified without rediscovery.
5. Owner publication is allowed only when source freshness, policy gates, and warning boards are green or explicitly retained with no publication authority.
6. The system can recover safely because every production write is backup-first, rollback-documented, and post-apply verified.

`10/10` is not "no warnings exist." It means every warning is either resolved or intentionally classified, visible, non-blocking for the chosen scope, and backed by an accepted contract.

## Gate Colors

Use these labels consistently:

| Gate | Meaning | Allowed next action |
|---|---|---|
| `GREEN` | The gate passed for its declared scope with evidence. | Continue to dependent gates. |
| `YELLOW` | Useful progress exists, but a blocker, owner decision, CodeCaptain decision, source gap, or retained-warning contract remains. | Continue only on independent read-only/copied-temp lanes; do not publish or production-apply based on this gate. |
| `RED` | Unsafe, contradictory, missing required authority, or protected-surface drift. | Stop and repair before proceeding. |
| `GREEN_FOR_SCOPE_ONLY` | The gate is green for a deliberately narrowed scope. | Continue only if every downstream artifact preserves the scope label. |
| `COPIED_TEMP_GREEN_PROOF` | A copied DB proof passed all required validators for the declared scope. | Prepare CodeCaptain review or production preflight, not production apply by itself. |
| `PRODUCTION_GREEN` | The approved production boundary passed post-apply validators. | May proceed to scheduler/owner-publication gates if those also pass. |

## Non-Negotiable Safety Contract

The project cannot be `10/10` unless these are true:

- `--help` or equivalent help/inspection commands never write data.
- All production write scripts are dry-run by default.
- Every production write requires an explicit write-enable environment gate plus `--apply` or equivalent.
- Every production DB write is backup-first and records backup path, SHA, integrity result, and rollback command.
- No workbook mutation happens without workbook SHA before/after evidence and the Excel UI contract.
- No scheduler, LaunchAgent, cron, browser, WebUI, Kaspi/API, ad-platform, bank, cash, supplier, PO, stock, price, or owner-publication write happens without exact owner approval for that surface.
- Copied-temp proof is never described as production truth.
- Scoped proof is never described as full-scope proof.
- Missing ads spend is never treated as zero spend without source evidence.
- API lifecycle evidence is never promoted into WebUI `status_change_at` truth without exact WebUI evidence or an accepted non-WebUI contract.

## Final Acceptance Matrix

### 1. Boundary And Write-Safety Gate

Goal: prove the system cannot accidentally mutate protected truth during inspection, proof, or help commands.

Required evidence:

- current `db/app.db` SHA;
- current workbook SHA for `excel_ui/SALES_KSP_CRM_V3.xlsx`;
- `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'` result is `ok`;
- holder/lsof check shows no unsafe active DB/workbook writer before production apply;
- SQLite sidecar check is clean or classified;
- `scripts/check_no_db_tracked.sh` passes;
- focused no-write tests for production-adjacent CLIs, including `scripts/generate_po_dashboard_data.py --help`;
- write-gating manifest review for any script that can touch production DB, workbook, scheduler, external accounts, stock, PO, cash, price, or publication.

Minimum tests:

```text
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
pytest -q tests/test_generate_po_dashboard_data_help_no_write.py
python3 scripts/validate_write_side_gating.py --strict
```

Required final artifact:

`WRITE_SAFETY_AND_BOUNDARY_GATE.json`

Acceptance:

- no hidden writes from help/inspection commands;
- no untracked or staged production DB file;
- all write-capable commands are gated, dry-run by default, and documented.

### 2. Source Truth Freshness Gate

Goal: prove every required source domain is fresh enough for the as-of date or explicitly retained as non-publication.

Required source domains:

- `src_ab_db_operational_truth`;
- `src_bank_manual_ingest`;
- `src_ecommerce_po_artifacts`;
- `src_facebook_ads_external_ads`;
- `src_inbound_workbook`;
- `src_payment_evidence_root`;
- `src_sourcing_research_supplier_routes`;
- `src_web_automation_kaspi_marketing_directapi`;
- order-entry / Kaspi order API source truth;
- WebUI ArchiveOrders lifecycle/status source truth for the declared store scope.

Minimum tests:

```text
python3 scripts/materialize_policy_source_freshness.py --db <copied-db> --as-of <YYYY-MM-DD> --dry-run --json
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
```

Required final artifacts:

- `SOURCE_FRESHNESS_ACCEPTED_PACKETS_MATRIX.tsv`;
- `SOURCE_FRESHNESS_BLOCKER_MATRIX.tsv`;
- `POLICY_GATE_MATRIX.tsv`;
- `OWNER_PUBLICATION_STILL_BLOCKED.md` when any publication gate remains blocked.

Acceptance:

- all required sources are `FRESH` for the declared as-of window; or
- retained sources are explicitly labeled and cannot authorize publication or production apply.

### 3. Orders, Sales, And Lifecycle Gate

Goal: prove orders and sales facts are current, identity-safe, and lifecycle/status truth is not invented.

Required evidence:

- Kaspi order headers and order entries are current for the proof window;
- `sales_fact_v2` or successor sales fact is current for the same window;
- header-only rows, product-identity quarantines, lifecycle residuals, and cancellation rows are either resolved or retained visibly;
- WebUI status-ledger provenance includes source file SHA, `requested_since`, `requested_until`, `window_since`, and `window_until`;
- scoped status-ledger proof states exact store scope.

Minimum tests:

```text
python3 scripts/validate_order_entries_freshness.py --strict
python3 scripts/validate_day_complete.py --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_sales_truth_consumers.py
python3 scripts/validate_cogs_completeness_by_month.py --strict
```

Required final artifacts:

- `ORDER_ENTRY_FRESHNESS_REPORT.json`;
- `DAY_COMPLETE_REPORT.json`;
- `STATUS_LEDGER_SCOPE_DECLARATION.md`;
- `LIFECYCLE_RESIDUAL_BLOCKER_MATRIX.tsv`;
- `SALES_FACT_IDENTITY_QUARANTINE_REPORT.tsv`.

Acceptance:

- all orders in the declared business window are represented without row loss;
- all lifecycle/status facts are source-backed or retained;
- no source status date is synthesized from a different source class without an accepted contract.

### 4. Ads Truth Gate

Goal: prove ads source truth, spend reality, offer universe coverage, and product-code mapping are current for the declared business scope.

Required evidence:

- STOREB business identity remains separate from `UNIVERSAL` login/switcher access identity;
- STOREB/ACMEWEAR/Meta or required store scopes have fresh evidence for the declared window;
- product-code mappings are exact, owner-confirmed, or retained visibly;
- missing spend is not zeroed;
- ad platform writes, bid changes, and budget changes are out of scope unless explicitly approved later.

Minimum tests:

```text
python3 scripts/validate_ads_sidecar_readiness.py --strict
python3 scripts/validate_ads_offer_universe_coverage.py --strict
python3 scripts/validate_ads_spend_reality.py --strict
python3 scripts/validate_ads_source_packet_contract.py --strict
```

Required final artifacts:

- `ADS_SOURCE_FRESHNESS_PACKET.json`;
- `ADS_PRODUCT_CODE_MAPPING_MATRIX.csv`;
- `ADS_UNMAPPED_POSITIVE_SPEND.csv`;
- `ADS_SPEND_REALITY_REPORT.json`;
- `ADS_OFFER_UNIVERSE_REPORT.json`.

Acceptance:

- ads validators pass for the declared scope;
- any unmapped positive spend is zero rows or explicitly retained as non-publication;
- copied-temp ads proof is not treated as ad-platform authority.

### 5. Cashflow And Bank Gate

Goal: prove owner cash and cashflow decisions are grounded in current account truth, not stale/manual drift.

Required evidence:

- actual vs modelled cashflow separation;
- latest statement/account-balance date per store/account;
- manual bank/cash snapshot freshness;
- rolling 14-day Kaspi sync or explicit retained blocker per store;
- compact SKU COGS/unit-economics gaps resolved or retained visibly;
- reserve/buffer treatment is explicit and not mixed into spendable cash.

Minimum tests:

```text
python3 scripts/validate_cashflow_invariants.py
python3 scripts/validate_cashflow_actual_model_separation.py
python3 scripts/validate_order_cashflow_coverage.py --strict
python3 scripts/validate_monthly_cash_reconciliation.py --strict
```

Required final artifacts:

- `CASHFLOW_SOURCE_FRESHNESS_REPORT.json`;
- `BANK_BALANCE_SNAPSHOT_EVIDENCE.tsv`;
- `CASHFLOW_ACTUAL_MODEL_SEPARATION_REPORT.json`;
- `COGS_UNIT_ECONOMICS_BLOCKER_MATRIX.tsv`.

Acceptance:

- every owner-visible cash number has source date, source class, and trust label;
- no stale or partial-range rebuild resets opening balances;
- reserve deposits/buffers are classified separately from available operating cash.

### 6. Stock, PO, And Inbound Gate

Goal: prove the system can make PO and stock decisions from fresh stock truth and accepted inbound/COGS economics.

Required evidence:

- stock snapshot is fresh against cutoff;
- operational stock ledger is current and internally consistent;
- PO dashboard invariants pass;
- day-complete and lifecycle blockers do not hide shipped/cancelled/returned truth;
- PO/inbound owner facts are accepted for the declared scope;
- no PO commitment or stock change is implied by proof.

Minimum tests:

```text
python3 scripts/validate_operational_stock_integration_gates.py --strict
python3 scripts/validate_stock_ledger.py --strict
python3 scripts/validate_po_dashboard_invariants.py --strict
python3 scripts/validate_po_contract.py --strict
python3 scripts/validate_po_money_gate.py --strict
```

Required final artifacts:

- `PO_STOCK_FRESHNESS_AND_PRODUCTION_READINESS_RERUN.json`;
- `STOCK_SNAPSHOT_FRESHNESS_REPORT.json`;
- `PO_DASHBOARD_INVARIANTS_REPORT.txt`;
- `PO_INBOUND_ACCEPTED_FACTS_MATRIX.tsv`;
- `PO_AUTHORITY_BLOCKERS.md`.

Acceptance:

- PO production-readiness gate is green for the declared scope;
- or PO remains visibly blocked and cannot authorize purchase, supplier payment, or stock mutation.

### 7. Exception Queue Gate

Goal: prove all decision blockers are visible, owned, and not silently leaking into green outputs.

Required evidence:

- exception queue schema and open rows validated;
- all high-risk stock/cash/identity/lifecycle exceptions have owner/source route;
- retained warnings are allowed only if they do not affect the declared output scope.

Minimum tests:

```text
python3 scripts/validate_exception_queue_db.py --strict
python3 scripts/validate_exceptions_schema.py --strict
python3 scripts/materialize_negative_ledger_exceptions.py --dry-run --json
```

Required final artifacts:

- `EXCEPTION_QUEUE_STATUS.json`;
- `RETAINED_WARNING_BOARD.md`;
- `OWNER_ACTION_LIST.md`.

Acceptance:

- no hidden `RED` or unclassified `HIGH` exception remains in any output claimed green;
- retained warnings are visible in owner and CodeCaptain packs.

### 8. Daily Business Operations Gate

Goal: prove the daily live workflow can run safely and be paused/resumed quickly.

Required workflows:

- order fetching;
- CRM / Google Board append;
- employee size-entry wait state;
- ready-button / bundling trigger;
- waybill/PDF generation;
- Telegram PDF bundle sending;
- daily survival brief;
- all-business automation pause/resume;
- scheduler heartbeat validation.

Minimum tests:

```text
python3 scripts/manage_business_automation.py status
python3 scripts/validate_scheduler_heartbeat.py --strict
python3 scripts/validate_google_closeout_expected_orders.py --strict
python3 scripts/validate_daily_ops_report.py --strict
python3 scripts/validate_sales_vs_waybill_parity.py --strict
python3 scripts/validate_shipped_truth_crm_waybill.py --strict
```

Required final artifacts:

- `DAILY_OPS_E2E_SMOKE_REPORT.json`;
- `AUTOMATION_PAUSE_RESUME_EVIDENCE.md`;
- `TELEGRAM_BUNDLE_SEND_EVIDENCE.md`;
- `CRM_GOOGLE_BOARD_APPEND_EVIDENCE.md`;
- `SCHEDULER_HEARTBEAT_REPORT.json`.

Acceptance:

- normal daily workflow can run without agent rediscovery;
- pause and resume are documented, tested, and operator-readable;
- no scheduled automation runs during frozen proof windows unless explicitly resumed.

### 9. Full Copied-Temp MVOS Proof Gate

Goal: prove the complete decision system can pass on a copied DB before any production apply.

Required evidence:

- copied DB created from current production SHA;
- copied DB integrity before and after proof;
- all accepted source packets/materializers applied only to copied DB;
- full validator matrix run;
- warning/blocker board generated;
- scope labels preserved.

Minimum tests:

```text
sqlite3 -readonly <copied-db> 'PRAGMA integrity_check;'
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
python3 scripts/validate_day_complete.py --db <copied-db> --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_po_dashboard_invariants.py --db <copied-db> --strict
python3 scripts/validate_ads_offer_universe_coverage.py --db <copied-db> --strict
python3 scripts/validate_ads_spend_reality.py --db <copied-db> --strict
python3 scripts/validate_exception_queue_db.py --db <copied-db> --strict
```

Required final artifacts:

- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json`;
- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md`;
- `VALIDATOR_EXIT_MATRIX.tsv`;
- `RETAINED_BLOCKER_BOARD.md`;
- `COPIED_DB_BOUNDARY_SHA256.tsv`.

Acceptance:

- `COPIED_TEMP_GREEN_PROOF` only if every required validator passes for the declared scope and no unaccepted retained blocker affects the claimed output;
- otherwise the board must be `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

### 10. Production Preflight And Apply Gate

Goal: prove the production apply path is safe, explicit, reversible, and reviewed.

Required evidence before apply:

- CodeCaptain reviewed the current copied-temp proof and production-preflight packet;
- exact owner approval phrase names the DB path, pre-SHA, scope, row counts, allowed script, and forbidden surfaces;
- fresh DB/workbook SHA and DB integrity;
- holder/lsof check;
- backup path, backup SHA, backup integrity;
- rollback command;
- dry-run result exactly matches expected apply result;
- no unrelated production surface drift.

Minimum tests:

```text
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --strict
<apply-script> --dry-run --json
```

Required final artifacts:

- `PRODUCTION_PREFLIGHT_PACKET.md`;
- `OWNER_APPROVAL_PHRASE_REQUEST.md`;
- `PRODUCTION_BACKUP_AND_ROLLBACK.md`;
- `DRY_RUN_EXPECTED_DIFF.json`.

Acceptance:

- no production apply starts without exact owner phrase;
- apply is serialized;
- apply touches only the approved surface;
- rollback is practical and tested enough for the risk level.

### 11. Post-Apply Production Validation Gate

Goal: prove production truth still matches the copied-temp proof after an approved apply.

Required evidence:

- production DB integrity after apply;
- protected SHA after apply;
- exact row counts or diff expected vs actual;
- same validator matrix rerun on production;
- no workbook/scheduler/external drift unless explicitly approved;
- release anchor with rollback pointer.

Minimum tests:

```text
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
scripts/check_no_db_tracked.sh
python3 scripts/validate_policy_source_freshness.py --db db/app.db --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict --json
pytest -q
```

Required final artifacts:

- `POST_APPLY_VALIDATION_MATRIX.tsv`;
- `PRODUCTION_DIFF_ACTUAL_VS_EXPECTED.json`;
- `RELEASE_ANCHOR.md`;
- `ROLLBACK_POINTER.md`.

Acceptance:

- production validators match the reviewed copied-temp proof;
- any mismatch is `RED` until repaired or rolled back.

### 12. Owner Publication And Autonomy Gate

Goal: prove the owner-facing system can publish/send only decision-grade outputs.

Required evidence:

- all publication policy gates pass;
- retained blockers are absent or explicitly excluded from the published scope;
- owner-facing report includes source dates, trust labels, and warning board;
- scheduler/automation heartbeat is healthy;
- daily workflow can run without intervention;
- escalation rules are documented for high-risk pauses only.

Minimum tests:

```text
python3 scripts/validate_profit_publication_integrity.py --strict
python3 scripts/validate_production_readiness.py --strict
python3 scripts/validate_scheduler_heartbeat.py --strict
python3 scripts/run_end_of_day.py --verbose
```

Required final artifacts:

- `OWNER_PUBLICATION_GREEN_PACKET.md`;
- `DAILY_AUTONOMY_RUNBOOK_CURRENT.md`;
- `SCHEDULER_HEARTBEAT_REPORT.json`;
- `OWNER_VISIBLE_WARNING_BOARD.md`.

Acceptance:

- owner publication/send is allowed only after this gate is green;
- the system can run the daily business decision loop repeatedly without manual debugging.

## Completion Score Model

Use this score model only as planning telemetry. The gate outputs remain the authority.

| Score | Meaning |
|---|---|
| `0/10` | Repo cannot be trusted for current decisions. |
| `3/10` | Some source ingestion and dashboards exist, but truth is stale or manual. |
| `5/10` | Core validators exist and partial copied-temp proofs work, but major source/policy blockers remain. |
| `7/10` | Most domains have source-backed paths; copied-temp proof can clear important slices; production and owner publication remain blocked. |
| `8/10` | C3/source freshness, PO/stock, ads, cash, lifecycle, and daily ops gates are mostly green or properly retained. |
| `9/10` | Full copied-temp MVOS proof and CodeCaptain review are green; production preflight is ready or completed. |
| `10/10` | Production post-apply validation, owner publication, scheduler/daily autonomy, rollback, and monitoring are green and repeatable. |

## Agent Execution Rules

Every implementation agent working toward this contract must:

- state which gate it is trying to move;
- read the owning docs for that gate;
- write evidence under a timestamped evidence folder or assigned handoff folder;
- include a standalone `Gate:` line in the closeout;
- keep process-green separate from domain-green;
- keep copied-temp proof separate from production truth;
- stop at `YELLOW` or `RED` instead of forcing a fake green;
- list exact commands run;
- list exact artifacts created;
- list protected-surface status;
- list the next smallest safe action.

## CodeCaptain Review Questions

Before this document is approved as canonical, CodeCaptain should answer:

1. Is this complete enough to define `10/10` for the Autonomous_business system?
2. Are any gates missing, redundant, too abstract, or impossible to verify?
3. Are the minimum tests practical and correctly mapped to domains?
4. Should full five-store status-ledger proof be mandatory for `10/10`, or can a scoped status ledger be accepted if the business scope excludes `11KZ` and `MELVIS`?
5. Is owner publication correctly separated from copied-temp proof and production apply?
6. Are production preflight/apply/rollback gates strict enough?
7. What exact changes should be made before the human owner approves this as the final completeness contract?
