# MVOS 10/10 Decision-Grade Acceptance Contract

Status: `CODECAPTAIN_REVIEWED_CANONICAL_CANDIDATE_PENDING_OWNER_APPROVAL`

Created: `2026-05-18`

Repo: `~/Docs/Autonomous_business`

CodeCaptain review source:

`~/Docs/Oracle/Autonomous_business/2026-05-18/154628_TASK-000_mvos-10-out-of-10-acceptance-contract-codecaptain-review/Answer/Code Captain_18.05.2026_16_16_34.md`

This document is the corrected implementation target after CodeCaptain's `YELLOW_APPROVE_AFTER_SPECIFIC_EDITS` review. It is not a production-write, scheduler, external-write, owner-publication, cash, PO, ad-spend, price, or stock authorization.

It becomes the final accepted `10/10` completeness contract only after explicit owner approval. Until then, agents may use it as the implementation target for read-only analysis, copied-temp proof, local code/test hardening, contract docs, evidence packaging, and review packets.

Current owner-answer overlays are canonical inputs for copied-temp/read-only implementation lanes and must be read before agents re-ask already answered owner questions:

- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260517.md`
- `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/OWNER_QA_PRIORITY_20260518_RETAINED_BLOCKERS.md`

The May 18 overlay includes timestamped owner answers for the active three-store scope, `11KZ`/`MELVIS` inactivity, May 18 no-new-payment bridge, latest `Cash_Balances` with non-spendable reserve, STOREB Line52 code mapping, PO-4.0 Line61 23-unit shortage, and retained 9 high-stock exceptions.

## Plain-English Definition

The project is `10/10` when the repo can safely run the daily business decision loop from source truth to owner/operator decisions without rediscovery, hidden stale data, mixed truth sources, silent mutations, or false-green outputs.

A `10/10` system:

1. Declares the exact business scope it is operating.
2. Uses `db/app.db` as operational truth.
3. Keeps Excel/workbooks as UI, input, or reference unless separately authorized.
4. Uses accepted source contracts for every external source, manual source, substitution, exclusion, or retained blocker.
5. Runs copied-temp proof before production apply.
6. Runs production apply only after explicit owner approval and backup/rollback gates.
7. Publishes owner outputs only when publication gates pass.
8. Keeps retained blockers visible.
9. Can run repeatedly on schedule or operator trigger without debugging.
10. Blocks cash, PO, ad spend, price, stock, workbook, scheduler, and external writes unless separately authorized.

`10/10` does not mean no warning exists. It means every warning is resolved, retained under accepted contract, scoped out, or visibly blocks the relevant decision.

## Gate Labels

| Gate | Meaning | Allowed next action |
| --- | --- | --- |
| `GREEN` | Passed for the declared scope with evidence. | Continue to dependent gates. |
| `YELLOW` | Useful progress exists, but a blocker, source gap, owner decision, CodeCaptain decision, or retained contract remains. | Continue only on independent read-only, copied-temp, or review-only lanes. |
| `RED` | Unsafe, contradictory, missing required authority, or protected-surface drift. | Stop and repair before proceeding. |
| `GREEN_FOR_SCOPE_ONLY` | Passed only for an explicitly narrowed scope. | Continue only if every downstream artifact preserves the scope label. |
| `COPIED_TEMP_GREEN_PROOF` | A copied DB proof passed all required validators for the declared scope. | Prepare CodeCaptain review or production preflight; never production apply by itself. |
| `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` | Copied-temp proof is useful, but retained blockers remain. | Prepare blocker repair plan or CodeCaptain packet; do not publish or apply. |
| `PRODUCTION_GREEN` | Approved production boundary passed post-apply validators. | May proceed to release, repeated-run, scheduler, and owner-publication gates if those also pass. |

## Non-Negotiable Safety Contract

The project cannot be `10/10` unless all of these are true:

- `--help` and equivalent help/inspection commands never write data.
- All production write scripts are dry-run by default.
- Every production write requires an explicit write-enable environment gate plus `--apply` or equivalent.
- Every production DB write is backup-first and records backup path, SHA, integrity result, and rollback command.
- No workbook mutation happens without workbook SHA before/after evidence and the Excel UI contract.
- No scheduler, LaunchAgent, cron, browser, WebUI, Kaspi/API, ad-platform, bank, cash, supplier, PO, stock, price, or owner-publication write happens without exact owner approval for that surface.
- Copied-temp proof is never described as production truth.
- Scoped proof is never described as full-scope proof.
- Missing ads spend is never treated as zero spend without source evidence.
- API lifecycle evidence is never promoted into WebUI `status_change_at` truth without exact WebUI evidence or an accepted non-WebUI contract.
- Cash, PO, ad-spend, price, stock, and external actions each require separate business-action authority unless a reviewed automation contract explicitly covers the action.

## Scope Profile Gate

Every MVOS proof must declare exactly one scope profile.

### `MVOS_SCOPE_FULL_FIVE_STORE`

Stores:

- `STOREB`
- `ACMEWEAR`
- `UNIVERSAL`
- `11KZ`
- `MELVIS`

Requirements:

- full five-store status-ledger continuity;
- source freshness for all in-scope stores;
- no owner-facing claim may exclude 11KZ or MELVIS.

### `MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE`

Stores:

- `STOREB`
- `ACMEWEAR`
- `UNIVERSAL`

Required disclosure in every downstream artifact:

```text
SCOPED_STATUS_LEDGER_STOREB_ACMEWEAR_UNIVERSAL_ONLY
11KZ_AND_MELVIS_EXCLUDED_FROM_CURRENT_OPERATING_SCOPE
NO_FULL_FIVE_STORE_STATUS_LEDGER_GREEN
```

Acceptance:

- no proof may claim full-business green unless the scope profile supports it;
- owner-facing outputs must show the scope profile;
- scoped proof may be `GREEN_FOR_SCOPE_ONLY`, never full five-store green.

Required artifacts:

- `MVOS_SCOPE_PROFILE_DECLARATION.md`
- `MVOS_SCOPE_PROFILE_DECLARATION.json`

## Source Contract Registry Gate

All source substitutions, exclusions, retained blockers, owner-confirmed mappings, manual source routes, copied-temp-only contracts, and production-eligible contracts must be registered.

Required registry:

```text
docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
```

Every contract entry must include:

- `contract_id`
- `domain`
- `scope_profile`
- `source_artifact_paths`
- `source_artifact_sha256`
- `proof_scope`
- `production_authority`
- `owner_publication_authority`
- `accepted_by`
- `accepted_at`
- `supersedes`
- `required_validators`
- `retained_blockers`
- `forbidden_claims`

Required tests:

```bash
python3 -m json.tool docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
python3 scripts/validate_mvos_source_contract_registry.py --strict
```

If a validator does not exist yet, it is a required implementation target and the gate cannot be final green until implemented and passing.

Acceptance:

- no materializer or validator uses an unregistered source substitution;
- duplicate active contracts for the same domain/scope are forbidden;
- copied-temp-only contracts cannot support production claims;
- retained blockers are tied to contract IDs.

## Boundary And Write-Safety Gate

Goal: prove protected truth cannot be mutated accidentally.

Required evidence:

- production DB SHA;
- protected workbook SHA;
- DB integrity `ok`;
- lsof/holder check;
- SQLite sidecar check;
- protected git status;
- no tracked production DB/workbook artifacts;
- all production-adjacent write scripts gated;
- help/inspection commands cannot write.

Required tests:

```bash
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
python3 scripts/validate_no_help_command_writes.py --strict
pytest -q tests/test_generate_po_dashboard_data_help_no_write.py
```

Required artifact:

- `WRITE_SAFETY_AND_BOUNDARY_GATE.json`

Acceptance:

- no hidden writes;
- every write path is dry-run by default;
- every write path requires env gate plus `--apply`;
- no help command writes data.

## Source Truth Freshness Gate

Goal: prove required sources are fresh for the declared as-of date and scope profile.

Required source domains:

- `src_ab_db_operational_truth`
- `src_bank_manual_ingest`
- `src_ecommerce_po_artifacts`
- `src_facebook_ads_external_ads` unless scoped out
- `src_inbound_workbook`
- `src_payment_evidence_root`
- `src_sourcing_research_supplier_routes`
- `src_web_automation_kaspi_marketing_directapi`
- order-entry / Kaspi API source truth
- WebUI ArchiveOrders lifecycle/status source truth

Required tests:

```bash
python3 scripts/materialize_policy_source_freshness.py \
  --db <copied-db> \
  --as-of <YYYY-MM-DD> \
  --source-contract-registry docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json \
  --proof-scope copied_temp \
  --dry-run \
  --json

python3 scripts/validate_policy_source_freshness.py \
  --db <copied-db> \
  --as-of <YYYY-MM-DD> \
  --strict \
  --json

python3 scripts/validate_policy_gate_results.py \
  --db <copied-db> \
  --strict \
  --json
```

Required artifacts:

- `SOURCE_FRESHNESS_ACCEPTED_PACKETS_MATRIX.tsv`
- `SOURCE_FRESHNESS_BLOCKER_MATRIX.tsv`
- `POLICY_GATE_MATRIX.tsv`

Acceptance:

- all required source rows are fresh; or
- retained source gaps are visible and block owner publication or production authority.

## Domain Gates

### Orders, Sales, And Lifecycle Gate

Required evidence:

- order headers current for proof window;
- order entries current for proof window;
- sales facts current for proof window;
- day-complete pass;
- lifecycle/status facts source-backed;
- cancellation rows source-backed or retained;
- no status date synthesized from unrelated evidence;
- status-ledger scope declared.

Required tests:

```bash
python3 scripts/validate_order_entries_freshness.py --strict
python3 scripts/validate_day_complete.py --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_sales_truth_consumers.py --strict
python3 scripts/validate_cogs_completeness_by_month.py --strict
```

Required artifacts:

- `ORDER_ENTRY_FRESHNESS_REPORT.json`
- `DAY_COMPLETE_REPORT.json`
- `STATUS_LEDGER_SCOPE_DECLARATION.md`
- `LIFECYCLE_RESIDUAL_BLOCKER_MATRIX.tsv`
- `SALES_FACT_IDENTITY_QUARANTINE_REPORT.tsv`

Acceptance:

- no order-row loss in scope;
- no lifecycle truth invented;
- warnings retained visibly.

### Ads Truth Gate

Required evidence:

- STOREB business identity separate from UNIVERSAL login/switcher identity;
- required stores have fresh ads source packets;
- Meta/Facebook either fresh or explicitly scoped out;
- product-code mappings accepted or retained;
- missing spend not zeroed;
- no ad-platform write authority.

Required tests:

```bash
python3 scripts/validate_ads_source_packet_contract.py --strict
python3 scripts/validate_ads_sidecar_readiness.py --strict
python3 scripts/validate_ads_offer_universe_coverage.py --strict
python3 scripts/validate_ads_spend_reality.py --strict
```

Required artifacts:

- `ADS_SOURCE_FRESHNESS_PACKET.json`
- `ADS_PRODUCT_CODE_MAPPING_MATRIX.csv`
- `ADS_UNMAPPED_POSITIVE_SPEND.csv`
- `ADS_SPEND_REALITY_REPORT.json`
- `ADS_OFFER_UNIVERSE_REPORT.json`

Acceptance:

- ads validators pass for declared scope; or
- ads retained blockers visibly block ads-dependent owner publication, profit-after-ads, and ad-spend decisions.

### Cashflow And Bank Gate

Required evidence:

- actual/model cash separation;
- current bank/cash balance source;
- payment evidence root current or no-new-payment contract accepted;
- COGS gaps resolved or retained;
- reserve/buffer separated from spendable cash;
- no missing costs treated as zero.

Required tests:

```bash
python3 scripts/validate_cashflow_invariants.py
python3 scripts/validate_cashflow_actual_model_separation.py --strict
python3 scripts/validate_order_cashflow_coverage.py --strict
python3 scripts/validate_monthly_cash_reconciliation.py --strict
```

Required artifacts:

- `CASH_RISK_DAILY_TRUST_BANNER.json`
- `CASHFLOW_SOURCE_TRUTH_MATRIX.tsv`
- `MISSING_COGS_BLOCKER_MATRIX.tsv`
- `PAYMENT_EVIDENCE_ROOT_STATUS.json`
- `BANK_BALANCE_SNAPSHOT_EVIDENCE.tsv`

Acceptance:

- cash source, payment source, and COGS gates match the declared scope;
- no cash movement is authorized by this gate.

### PO, Stock, And Inbound Gate

Required evidence:

- stock snapshot fresh for proof date;
- sales fact source is current and strict;
- stock ledger materialization is source-backed;
- inbound/PO facts are source-backed;
- PO dashboard invariants pass;
- day-complete dependencies resolved;
- no non-strict sales rebuild used as production truth.

Required tests:

```bash
python3 scripts/validate_po_dashboard_invariants.py --strict
python3 scripts/validate_inventory_snapshot_freshness.py --strict
python3 scripts/validate_stock_ledger_to_snapshot.py --strict
python3 scripts/validate_po_contract.py --strict
python3 scripts/validate_po_money_gate.py --strict
```

Required artifacts:

- `PO_STOCK_FRESHNESS_AND_PRODUCTION_READINESS_RERUN.json`
- `STOCK_SNAPSHOT_FRESHNESS_REPORT.json`
- `PO_DASHBOARD_INVARIANTS_REPORT.txt`
- `PO_INBOUND_ACCEPTED_FACTS_MATRIX.tsv`
- `PO_AUTHORITY_BLOCKERS.md`

Acceptance:

- PO production-readiness gate passes for declared scope; or
- PO/stock decisions remain blocked.

### Exception Queue And Retained Blocker Gate

Required evidence:

- exception queue schema valid;
- all `HIGH`/`RED` rows classified;
- retained blockers tied to contracts;
- no retained blocker hidden in green output.

Required tests:

```bash
python3 scripts/validate_exception_queue_db.py --strict
python3 scripts/validate_exceptions_schema.py --strict
python3 scripts/validate_retained_blocker_board.py --strict
```

Required artifacts:

- `EXCEPTION_QUEUE_STATUS.json`
- `RETAINED_BLOCKER_BOARD.md`
- `RETAINED_BLOCKER_BOARD.json`
- `OWNER_ACTION_LIST.md`

Acceptance:

- no hidden unclassified high-risk exception;
- every retained warning visible in owner/operator output.

## Owner Decision Surface Gate

Required surfaces:

- Cash Risk Daily
- Daily Survival Brief
- Stock/Order Risk
- Ads/Profit Readiness
- PO/Inbound Readiness

Each surface must show:

- scope profile;
- DB SHA;
- workbook SHA;
- source dates;
- warning board;
- allowed decisions;
- blocked decisions;
- evidence paths;
- owner/operator action list.

Required tests:

```bash
python3 scripts/validate_owner_decision_surface.py --surface cash_risk_daily --strict
python3 scripts/validate_owner_decision_surface.py --surface daily_survival_brief --strict
python3 scripts/validate_owner_decision_surface.py --surface stock_order_risk --strict
python3 scripts/validate_owner_decision_surface.py --surface ads_profit_readiness --strict
python3 scripts/validate_owner_decision_surface.py --surface po_inbound_readiness --strict
```

Required artifact:

- `OWNER_DECISION_SURFACE_ACCEPTANCE_MATRIX.tsv`

Acceptance:

- owner/operator can act only on decisions marked allowed;
- blocked decisions cannot be implied as allowed;
- no surface implies unauthorized cash, PO, ad, price, stock, workbook, scheduler, external-system, or owner-publication action.

## Full Copied-Temp MVOS Proof Gate

Required evidence:

- copied DB created from current production SHA;
- copied DB integrity before and after;
- source contracts applied only to copy;
- full validator matrix run;
- retained blockers visible;
- scope labels preserved.

Required tests:

```bash
sqlite3 -readonly <copied-db> 'PRAGMA integrity_check;'
python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json
python3 scripts/validate_day_complete.py --db <copied-db> --strict
python3 scripts/validate_status_ledger_continuity.py --strict
python3 scripts/validate_po_dashboard_invariants.py --db <copied-db> --strict
python3 scripts/validate_ads_offer_universe_coverage.py --db <copied-db> --strict
python3 scripts/validate_ads_spend_reality.py --db <copied-db> --strict
python3 scripts/validate_exception_queue_db.py --db <copied-db> --strict
python3 scripts/validate_owner_decision_surface.py --surface cash_risk_daily --strict
python3 scripts/validate_owner_decision_surface.py --surface daily_survival_brief --strict
python3 scripts/validate_owner_decision_surface.py --surface stock_order_risk --strict
python3 scripts/validate_owner_decision_surface.py --surface ads_profit_readiness --strict
python3 scripts/validate_owner_decision_surface.py --surface po_inbound_readiness --strict
```

Required artifacts:

- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json`
- `FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md`
- `VALIDATOR_EXIT_MATRIX.tsv`
- `RETAINED_BLOCKER_BOARD.md`
- `COPIED_DB_BOUNDARY_SHA256.tsv`

Acceptance:

- `COPIED_TEMP_GREEN_PROOF` only if every required validator passes for declared scope and no unaccepted retained blocker affects claimed output;
- otherwise proof must be `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

## Production Preflight And Apply Gate

Production apply is out of scope until CodeCaptain review and exact owner approval exist.

Required before apply:

- CodeCaptain review of copied-temp proof and production preflight;
- exact owner phrase;
- fresh DB/workbook SHA;
- DB integrity;
- lsof/holder check;
- SQLite sidecar check;
- backup path/SHA/integrity;
- rollback command;
- exact dry-run diff;
- manifest-covered write commands.

Required tests:

```bash
scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
<apply-script> --dry-run --json
```

Required artifacts:

- `PRODUCTION_PREFLIGHT_PACKET.md`
- `OWNER_APPROVAL_PHRASE_REQUEST.md`
- `PRODUCTION_BACKUP_AND_ROLLBACK.md`
- `DRY_RUN_EXPECTED_DIFF.json`
- `WRITE_COMMAND_MANIFEST.tsv`

Acceptance:

- production apply never starts without exact owner phrase;
- apply touches only approved surfaces;
- rollback is practical;
- every command matches reviewed command list.

## Post-Apply Release Anchor Gate

This gate can run only after a separately approved production apply.

Required evidence:

- production DB integrity after apply;
- protected workbook SHA after apply;
- row-level expected vs actual diff;
- full validator matrix rerun;
- release anchor;
- rollback pointer;
- git HEAD / repo status;
- source contract registry hash.

Required tests:

```bash
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
scripts/check_no_db_tracked.sh
python3 scripts/validate_policy_source_freshness.py --db db/app.db --as-of <YYYY-MM-DD> --strict --json
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict --json
pytest -q
```

Required artifacts:

- `POST_APPLY_VALIDATION_MATRIX.tsv`
- `PRODUCTION_DIFF_ACTUAL_VS_EXPECTED.json`
- `RELEASE_ANCHOR.md`
- `RELEASE_ANCHOR.json`
- `ROLLBACK_POINTER.md`

Acceptance:

- production validators match reviewed copied-temp proof;
- mismatches are `RED` until repaired or rolled back.

## Repeated-Run And Autonomy Gate

Required evidence:

- at least 3 consecutive successful validate-only daily runs for the declared scope;
- run status per day;
- no hidden manual interventions;
- scheduler/trigger behavior observed without mutation unless separately approved;
- pause/resume documented;
- owner/operator brief generated each day;
- retained blockers remain visible.

Required tests:

```bash
python3 scripts/validate_mvos_repeated_run.py --days 3 --strict
python3 scripts/validate_scheduler_heartbeat.py --strict
python3 scripts/manage_business_automation.py status
```

Required artifacts:

- `MVOS_REPEATED_RUN_MATRIX.tsv`
- `AUTOMATION_PAUSE_RESUME_EVIDENCE.md`
- `SCHEDULER_HEARTBEAT_REPORT.json`
- `DAILY_AUTONOMY_RUNBOOK_CURRENT.md`

Acceptance:

- daily loop is repeatable without rediscovery;
- owner/operator output remains stable;
- failures fail closed.

## Owner Publication And Live Authority Gate

Required evidence:

- all publication policy gates pass;
- owner decision surfaces pass;
- retained blockers absent or excluded from publication scope;
- source dates and scope labels visible;
- no business action authority implied unless explicitly approved.

Required tests:

```bash
python3 scripts/validate_profit_publication_integrity.py --strict
python3 scripts/validate_production_readiness.py --strict
python3 scripts/validate_owner_publication_packet.py --strict
python3 scripts/validate_external_write_boundaries.py --strict
```

Required artifacts:

- `OWNER_PUBLICATION_GREEN_PACKET.md`
- `OWNER_VISIBLE_WARNING_BOARD.md`
- `OWNER_DECISIONS_ALLOWED_BLOCKED_MATRIX.tsv`

Acceptance:

- owner publication/send allowed only after this gate is green;
- cash, PO, ad-spend, price, stock, and external write authority each require separate explicit approval unless covered by a reviewed automation contract.

## Completion Score Model

Scores are planning telemetry only. Gate outputs are authority.

| Score | Meaning |
| --- | --- |
| `7/10` | Review-only surfaces are useful, but major source blockers remain. |
| `8/10` | Source contracts are mostly accepted and copied-temp board proof is near green. |
| `9/10` | Full copied-temp proof is green and production preflight is ready or completed. |
| `10/10` | Production post-apply validation, owner publication, repeated daily run, rollback, monitoring, scheduler, and pause/resume proof are green for declared scope. |

## Final Acceptance Package

No `10/10` claim is valid without these artifacts for the declared scope:

```text
MVOS_10_OUT_OF_10_ACCEPTANCE_PACKET.md
MVOS_10_OUT_OF_10_ACCEPTANCE_PACKET.json
MVOS_SCOPE_PROFILE_DECLARATION.json
ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json
POST_APPLY_VALIDATION_MATRIX.tsv
RELEASE_ANCHOR.json
MVOS_REPEATED_RUN_MATRIX.tsv
OWNER_PUBLICATION_GREEN_PACKET.md
OWNER_DECISIONS_ALLOWED_BLOCKED_MATRIX.tsv
```

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
