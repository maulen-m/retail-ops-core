2‑Week Execution Board (A → C → B) — v2 (Ads WT‑informed, fail‑closed)
Purpose

Deliver the highest ROI “trust closure” improvements in 2 weeks with fail‑closed guarantees, minimal human time, and promotion‑grade evidence: (A) eliminate silent data mismatches and profit computed on partial truth, (C) integrate Ads spend into profit realism via read‑only sidecar consumption of the existing Ads WT v1 system, then (B) harden shipment runtime reliability and preflight blocks.

Context / Baseline (known-good foundations)

Main repo already has promotion‑grade ops/CI gates (headless + local strict chains).

Ads already exists as an isolated, safe worktree system (WT v1) with its own trust loop; the sprint should consume its outputs first rather than rebuild ingestion.

How to think about this document (the “efficient version”)

This board is not a strategy doc; it is a stop‑line execution queue.

Every item has: one measurable goal → concrete artifacts → one primary gate → rollback.

Progress must be tracked as a single source of truth:

GOALS.md: only a link + current sprint status summary (do not copy the whole board).

.claude/TASKS.md: one line per item (A1…B2) with status (TODO/DOING/DONE/ROLLED_BACK).

.claude/PROGRESS.md: daily timestamped updates with “what gate is green now”.

claude/journal.md: append‑only execution log (timestamped).

Non‑negotiables (fail‑closed)

No metric is allowed to silently degrade into “0” or “green” when inputs are missing or stale.

No write/apply actions are allowed without explicit env+apply gating.

No new production dependencies in CI: tests must use temp fixtures, not real DBs/workbooks.

Single‑agent sequential execution in one branch/worktree unless isolation is safer.

Global Validation / Gates (must remain green after every item)

python3 scripts/validate_params.py --strict

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q

python3 scripts/run_contract_suite.py --fixture small

python3 scripts/validate_single_truth_system.py

scripts/lint_docs.sh

scripts/check_no_db_tracked.sh

bash scripts/install_single_truth_ops_scheduler.sh --validate-only

python3 scripts/check_anchor_health.py --project-root <REPO_PATH>

python3 scripts/ops_status.py --project-root <REPO_PATH>

/tmp cwd‑independence stop‑line check for any scripts/tests that are import‑path sensitive.

Phase List (A → C → B)
P0 — Board Wiring + Evidence Discipline (Day 0–0.5)

Goal (measurable)
Board items are trackable, and evidence artifacts are standardized so we don’t “circle” problems.

Inputs

docs/ideas/PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_2026-02-21.md (this file)

.claude/{GOALS,PROGRESS,TASKS,ISSUES,DECISIONS}.md

claude/journal.md

Outputs (artifacts + exact paths)

Updated .claude/TASKS.md entries for: A1, A2, A3, C0, C1, C2, C3, B1, B2

Updated .claude/PROGRESS.md “Sprint A→C→B” header with a scoreboard

Updated .claude/DECISIONS.md with the Ads integration mode decision (see C0)

Evidence folder convention (per work item): exports/validation/board_2w_YYYY-MM-DD/<ITEM_ID>/...

Definition of Done
Accepted as done only when the board has a single authoritative status surface (in .claude/*) and every item has an explicit evidence location.

Validation/Gates

scripts/lint_docs.sh remains green after updates.

Rollback / backout strategy
Revert the docs-only commit(s) if it introduces lint failures or confusion.

Stop‑the‑line criteria

Any board item lacks an owner, artifact path, or primary gate.

A1 — Inbound Sheet Mismatch Detector (W1 D1–D2)

Goal (measurable)
Detect and fail‑closed on inbound reconciliation mismatches (e.g., PO-5.2 “3940 vs 3980” style drift) before publication.

Inputs

Inbound workbook anchor: config/anchors/INBOUND_CALENDAR_LATEST.xlsx (and related parsing logic)

Existing validators: scripts/validate_params.py, scripts/validate_single_truth_system.py

Outputs

New validator: scripts/validate_inbound_sheet_consistency.py

Tests: tests/test_validate_inbound_sheet_consistency.py

Runbook: docs/po/INBOUND_MISMATCH_RUNBOOK.md

Evidence: exports/validation/board_2w_YYYY-MM-DD/A1_inbound_mismatch/{targeted_red.md,targeted_green.md}

Definition of Done
Accepted as done only when:

The validator exits non‑zero on mismatch and produces a machine‑readable mismatch report.

The mismatch report includes at minimum: PO id / SKU / expected vs actual / source sheet(s).

The validator is wired into strict validation (directly or via a referenced strict gate).

Validation/Gates

Targeted test goes red first, then green.

Full global gate chain remains green.

Rollback
Revert the A1 commit(s) (validator + tests + docs). No schema migrations that cannot be reverted.

Stop‑the‑line

Any mismatch is detected but publication still proceeds (“soft warning” is not acceptable).

Any mismatch is silently coerced into a value.

A2 — Offer Linkage Strict Closure (W1 D2–D3)

Goal
No silent unresolved offer mappings in any publish path; unresolved linkage blocks downstream surfaces.

Inputs

Offer linkage logic (existing consumers + DB tables)

scripts/validate_params.py --strict and/or scripts/validate_single_truth_system.py

Outputs

Validator: scripts/validate_offer_linkage.py

Tests: tests/test_validate_offer_linkage.py

Contract doc: docs/offer/offer_linkage_contract.md

Evidence: exports/validation/board_2w_YYYY-MM-DD/A2_offer_linkage/...

Definition of Done
Accepted as done only when:

Any unresolved offer linkage in strict mode is a hard failure with a specific report.

At least one high‑risk consumer path is proven to refuse publishing without linkage.

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert A2 commit(s).

Stop‑the‑line

“Unresolved offers” appears anywhere in logs without a non‑zero exit and a report artifact.

A3 — Profit Hard‑Block Everywhere (COGS + Linkage) (W1 D3)

Goal
Profit/ROIC outputs can never be computed/published when prerequisites are unresolved (COGS unresolved, offer linkage unresolved, missing required anchors).

Inputs

Profit surfaces (dashboards/reports) and existing strict validators

COGS rules + inventory contracts (existing)

Outputs

Hardened validator/wiring: scripts/validate_cogs_integrity.py and integration points

Tests: tests/test_profit_hard_block_contract.py (new)

Contract doc: docs/profit/PROFIT_REALISM_CONTRACT.md

Evidence: exports/validation/board_2w_YYYY-MM-DD/A3_profit_hard_block/...

Definition of Done
Accepted as done only when:

Any profit surface produces N/A + explicit reason when prerequisites are missing, and strict mode fails closed.

A regression test proves that “unresolved prerequisites” cannot silently yield numeric profit.

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert A3 commit(s).

Stop‑the‑line

Any profit surface emits profit while unresolved prerequisites > 0.

C0 — Ads Integration Contract + Source‑of‑Truth Decision (W2 D1)

Goal
Lock the integration approach: consume Ads WT v1 outputs read‑only first; promotion is separate and optional.

Inputs

Ads WT contract (env/write gating; dry‑run default)

Main write‑side gating policies

Outputs

Contract doc: docs/marketing/ADS_SIDE_CAR_CONTRACT.md (main repo)

Tests: tests/test_ads_sidecar_contract.py

.claude/DECISIONS.md entry: “Ads integration mode = read‑only consumption; no bid writes”

Definition of Done
Accepted as done only when:

The contract explicitly forbids writes by default and defines how Ads DB/source is referenced (anchor or env var).

Tests enforce the contract (e.g., missing env var → fail‑closed for ads features, not silent zeros).

Validation/Gates

Contract test red→green.

Full global gate chain green.

Rollback
Docs/test revert.

Stop‑the‑line

Any plan merges Ads write capability into main without explicit gating + manifest + tests.

C1 — Ads Sidecar Ingest (Read‑Only, Coverage‑First) (W2 D1–D2)

Goal
Create a deterministic, read‑only ingest of ads spend/telemetry aggregates into main, with coverage and freshness reporting.

Inputs

Ads WT outputs source (read‑only): Ads DB or daily facts/report artifacts (must be referenced via anchor/env).

Main DB schema for daily metrics.

Outputs

Ingest script: scripts/sync_ads_sidecar.py (read‑only; no network; no writes outside main DB)

Tests: tests/test_sync_ads_sidecar.py (creates temp sqlite fixtures; no tracked .db)

Coverage report: exports/validation/board_2w_YYYY-MM-DD/C1_ads_sidecar/ads_coverage_report.md

(Optional) schema doc: docs/marketing/ADS_SIDE_CAR_SCHEMA.md

Definition of Done
Accepted as done only when:

If ads source is missing/stale → script fails closed (or writes explicit “missing/stale” state), never zeros.

Coverage report includes: % SKUs mapped, % spend attributable, top unmapped keys.

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert C1 commit(s). Ensure no irreversible DB migrations.

Stop‑the‑line

Any ads spend is treated as 0 due to missing input.

Any attempt to write to ads DB or external systems.

C2 — Publish profit_after_ads + Gating (W2 D2–D3)

Goal
Expose profit_after_ads (and optionally ROIC_after_ads) in decision surfaces with fail‑closed gating.

Inputs

Outputs of C1 (ads spend attribution table/state)

Profit surfaces / reporting scripts

Outputs

Builder: scripts/build_profit_after_ads.py

Tests: tests/test_profit_after_ads_contract.py

Contract doc: docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md

Evidence: exports/validation/board_2w_YYYY-MM-DD/C2_profit_after_ads/...

Definition of Done
Accepted as done only when:

profit_after_ads is N/A unless ads coverage + freshness gates pass.

The output explicitly states whether it is “ads‑backed” or “ads‑missing.”

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert C2 commit(s).

Stop‑the‑line

Any dashboard/report shows profit_after_ads without also showing ads data freshness/coverage state.

C3 — Discount / Effective‑Cost Realism Wiring (W2 D3)

Goal
Ensure discount periods (e.g., LINE61‑like multipliers) are applied consistently in profit_after_ads/ROIC_after_ads, with policy documented and test‑locked.

Inputs

Policy file (e.g., config/kaspi_ads_cost_adjustments.yaml from Ads WT—if promoted, keep it read‑only and doc‑owned)

C2 computation pipeline

Outputs

Policy wiring in profit_after_ads pipeline (no hidden defaults)

Tests: tests/test_ads_effective_cost_policy.py

Policy doc: docs/marketing/ADS_EFFECTIVE_COST_POLICY.md

Definition of Done
Accepted as done only when:

Multipliers are applied exactly as declared and tested for at least one known campaign class.

If policy file missing → fail closed for effective-cost outputs (do not guess).

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert C3 commit(s).

Stop‑the‑line

Any “effective cost” is computed with implicit/undocumented multipliers.

B1 — Waybill Runtime Health State Machine (W2 D4–D5)

Goal
Shipment runtime emits explicit health states (ok/delayed/api_error/schema_mismatch/etc.) and prevents silent partial runs.

Inputs

scripts/ship_orders_api.py

scripts/download_waybills_api.py

Outputs

Health state machine implementation + docs:

docs/ops/SHIPMENT_HEALTH_STATES.md

Tests:

tests/test_shipment_health_states.py

Evidence:

exports/validation/board_2w_YYYY-MM-DD/B1_waybill_health/...

Definition of Done
Accepted as done only when:

Health state is computed deterministically and surfaced to operator.

Failures are classified, not just “exception text.”

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert B1 commit(s).

Stop‑the‑line

Any shipment run can end in a “half‑done” state without explicit classification and non‑zero exit.

B2 — Pre‑Shipment Hard Preflight (W2 D5)

Goal
Block shipments unless critical gates are green (anchor health, required DB invariants, and runtime readiness checks).

Inputs

scripts/ship_orders_api.py

Existing preflight/ops scripts

Outputs

Preflight script: scripts/preflight_shipment.py

Tests: tests/test_shipment_preflight.py

Runbook: docs/ops/SHIPMENT_PREFLIGHT.md

Definition of Done
Accepted as done only when:

Shipments cannot proceed when preflight is red.

Preflight output explains exactly what is failing and where.

Validation/Gates

Targeted tests red→green.

Full global gate chain green.

Rollback
Revert B2 commit(s).

Stop‑the‑line

Shipment can run with known red preflight conditions.

Rollback / Release Discipline (applies to every phase)

Each phase is revertable via git revert <phase_commit(s)>.

Any PR must include:

evidence links under exports/validation/...

the exact gate commands + PASS summary

rollback steps and “minimum recheck” gates.

If attachments are missing — assumptions policy

Proceed with explicit assumptions in the phase artifact (doc/test header).

Default to fail‑closed behavior when input data, schema, or mapping is uncertain.

Never introduce “best guess” values into profit/cashflow outputs; emit N/A + reason.