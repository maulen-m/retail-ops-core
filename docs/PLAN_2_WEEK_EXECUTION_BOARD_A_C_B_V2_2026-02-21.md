PLAN_2_WEEK_EXECUTION_BOARD_A_C_B_V2_2026-02-21
Purpose

This plan is the promotion + operationalization board for the A→C→B sprint work (trust closure → ads profit realism → shipment safety). The implementation exists on branch codex/TASK-2w-board-ACB-v2-ads-sidecar; the remaining goal is to promote it safely to main, preserve fail‑closed behavior, and make the system operable with near‑zero human time.

How to think about this document (efficient / anti-circling)

This plan is the detailed execution board (phase definitions, gates, stop‑line criteria).

GOALS.md should remain a short index (10–20 lines) with links to this plan, not a duplicate of it.

All day‑to‑day progress is tracked in:

.claude/TASKS.md (canonical checklist)

.claude/PROGRESS.md (what is green/red now)

.claude/ISSUES.md (current blockers)

.claude/DECISIONS.md (locked decisions)

claude/journal.md (append‑only evidence trail, timestamped)

Global constraints (fail-closed / capital-safe)

Fail‑closed always wins over speed.

No write/apply actions unless explicitly enabled by dual gating (flag + env) and documented runbook.

No “synthetic defaults” for money semantics (ads spend, profit, cashflow): use N/A + reason.

No absolute personal paths in docs. Use repo‑relative paths, anchor contracts, env vars.

Primary gates (must be green for promotion)

G0 — Strict validation chain

python3 scripts/validate_params.py --strict

G1 — Test suite

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q

G2 — Contract suite

python3 scripts/run_contract_suite.py --fixture small

G3 — System validation

python3 scripts/validate_single_truth_system.py

G4 — Docs + repo hygiene

bash scripts/lint_docs.sh

bash scripts/check_no_db_tracked.sh

G5 — Ops stop-the-line checks

bash scripts/install_single_truth_ops_scheduler.sh --validate-only

python3 scripts/check_anchor_health.py --project-root <REPO_PATH>

python3 scripts/ops_status.py --project-root <REPO_PATH>

python3 scripts/preflight_shipment.py --project-root <REPO_PATH> --json (must be green on a healthy environment)

Phase list
P0 — Promotion to main (single PR, agent-owned)

Goal (measurable)
Promote the branch into main via one PR with decision‑grade evidence and rollback instructions.

Inputs

Branch: codex/TASK-2w-board-ACB-v2-ads-sidecar

Existing evidence folder: exports/validation/board_2w_2026-02-21/

Existing contracts/runbooks (see P1–P3 phases)

Outputs (artifacts + exact paths)

Promotion evidence doc: docs/OPS_ROLLOUT_EVIDENCE_TASK_392_ACB_V2_PROMOTION_2026-02-21.md

PR link + merge SHA recorded in the evidence doc

.claude/PROGRESS.md, .claude/DECISIONS.md, .claude/ISSUES.md, .claude/TASKS.md updated for post‑merge state

claude/journal.md appended with timestamps + gate summaries

Definition of Done (Accepted as done only when…)

PR is merged to main and the evidence doc contains:

links to evidence files under exports/validation/board_2w_2026-02-21/

a checklist showing G0–G5 are green

rollback commands (commit reverts + minimum recheck gates)

Validation/Gates

G0–G5 all green for the promotion commit set.

Rollback / backout strategy

Revert promotion commits (list exact SHAs in evidence doc). Minimum recheck after rollback: run G0 + G5.

Stop-the-line criteria

Any gate G0–G5 fails.

Any doc adds absolute personal paths.

Any code path introduces write/apply without explicit dual gating.

P1 — Trust closure operationalization (inbound + offer + profit)

Goal (measurable)
Ensure “truth closure” validators are enforced in strict flow and produce actionable reports when failing.

Inputs

Inbound anchors: config/anchors/INBOUND_CALENDAR_LATEST.xlsx (via anchor contract)

DB: db/app.db

Outputs

Runbooks remain canonical:

docs/po/INBOUND_MISMATCH_RUNBOOK.md

docs/offer/offer_linkage_contract.md

docs/profit/PROFIT_REALISM_CONTRACT.md

Strict chain reports include explicit failure reasons and pointers to runbooks.

Definition of Done

Strict chain fails closed when:

inbound sheets disagree

profit prerequisites are unresolved

Offer linkage: strict failure behavior is explicitly decided and documented:

either “default fail‑closed” OR “informational default with mandatory strict flag in publish paths”, with tests proving the publish path is blocked.

Validation/Gates

G0–G3 + targeted tests for inbound/offer/profit validators.

A regression test proves numeric profit cannot be emitted when prerequisites unresolved.

Rollback

Revert validator wiring changes only (surgical rollback; do not touch unrelated subsystems).

Stop-the-line

Any publish/decision surface shows numeric profit with unresolved prerequisites > 0.

P2 — Ads sidecar ops integration (read-only, no silent zeros)

Goal (measurable)
Ads spend is integrated into profit surfaces safely: profit_after_ads is never numeric unless the ads source contract is green.

Inputs

Ads source DB resolved by contract:

CLI --ads-db OR AB_ADS_DB_PATH OR default (Kaspi_marketing/db/kaspi_marketing.db)

Effective cost policy (optional):

AB_ADS_EFFECTIVE_COST_POLICY_PATH OR config/kaspi_ads_cost_adjustments.yaml

Outputs

Contract docs remain canonical:

docs/marketing/ADS_SIDE_CAR_CONTRACT.md

docs/marketing/PROFIT_AFTER_ADS_CONTRACT.md

docs/marketing/ADS_EFFECTIVE_COST_POLICY.md

Daily/weekly decision artifacts (e.g., business-insides outputs) surface:

ads status (available|unavailable) + reason

profit_after_ads is numeric only when status is available

Definition of Done

If ads source is missing/stale/future-skewed:

ads metrics are N/A (not 0)

profit_after_ads is N/A

output includes a clear reason string.

Validation/Gates

Targeted tests for ads sidecar contract + profit_after_ads contract + effective-cost policy.

Full gate chain (G0–G4) remains green.

Rollback

Revert ads sidecar integration commits; ensure no external DB mutations exist.

Stop-the-line

Any analytics surface treats missing ads as “0 spend”.

Any attempt to write to ads DB or network endpoints without explicit write gates.

P3 — Shipment runtime safety (no partial silent runs)

Goal (measurable)
Shipping/waybill workflows cannot run when the repo is in a red integrity state, and partial outcomes are deterministic and non‑zero exit.

Inputs

Shipment entrypoints:

scripts/ship_orders_api.py

scripts/download_waybills_api.py

excel_ui/run_build_waybills.command

Preflight: scripts/preflight_shipment.py

Outputs

Canonical runbooks:

docs/ops/SHIPMENT_HEALTH_STATES.md

docs/ops/SHIPMENT_PREFLIGHT.md

Machine-readable preflight report artifact supported via --json and --output.

Definition of Done

Shipment cannot proceed when preflight is red.

Any “partial/delayed/api_error/invalid_pdf” is classified and returns non‑zero.

Validation/Gates

Targeted tests for shipment health states + shipment preflight.

Full gate chain (G0–G4) remains green.

Rollback

Revert shipment preflight integration if it blocks incorrectly; minimum recheck: preflight must still exist as a manual gate.

Stop-the-line

Any shipment run can complete in a half‑done state with exit code 0.

Any bypass path is introduced that skips preflight.

If attachments are missing — assumptions policy

If evidence docs or validation artifacts referenced by this plan are missing, treat the phase as not done until recreated.

Default to fail‑closed behavior when data/schema/mapping is uncertain.

Never introduce “best guess” money/accounting values; emit N/A + reason and add a regression test.