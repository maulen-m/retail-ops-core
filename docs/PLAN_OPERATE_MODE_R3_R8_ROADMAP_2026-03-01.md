PLAN_OPERATE_MODE_R3_R8_ROADMAP_2026-03-01
Purpose

Shift from “continuous building” to Operate Mode: run the business with decision-grade outputs (BUSINESS_INSIDES economics + PO proposals) under fail-closed gates, minimal human time (0–5%), and staged execution safety (write canaries).

This plan assumes baseline engines are already green:

Ocean-drop truth alignment and drift gates are PASS.

BUSINESS_INSIDES economics publication is governed by docs/validation/BUSINESS_INSIDES_ECONOMICS_PUBLICATION_CONTRACT.md.

PO proposals + capital protection validator exist and are passing.

Phase List
R3 — Operate-Mode Adoption (process governance)

Goal (measurable)

100% of change sets include: ROI claim + gate transcript + rollback plan + explicit stop-line condition.

Inputs

docs/ops/RELEASE_POLICY_OPERATE_MODE.md

Existing strict gate chain.

Outputs

Enforcement artifacts:

docs/ops/RELEASE_POLICY_OPERATE_MODE.md (already exists; update only if missing enforcement details)

docs/ops/RELEASE_BUNDLE_TEMPLATE.md (NEW: copy/paste bundle template)

Evidence:

exports/validation/board_operate_mode_enforcement_<DATE>/full_gates_green_final.md

Definition of Done
Accepted as done only when:

A release-bundle template exists and is referenced by RELEASE_POLICY_OPERATE_MODE.md.

A CI or local validator checks bundle presence in PRs/releases (no silent skipping).

Validation/Gates

Baseline mandatory gates:

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q

python3 scripts/validate_params.py --strict

python3 scripts/validate_single_truth_system.py

bash scripts/lint_docs.sh

Rollback / Backout

Revert doc/template changes (no runtime state change).

Stop-the-line

Any PR/release without ROI claim + transcript path + rollback plan.

R3.1 — One-Command Operate Day Runner (daily decision loop)

Goal (measurable)

Single command produces a deterministic “operate day manifest” and stops on red:

GREEN only when all required validators pass.

RED otherwise, with explicit error list.

Inputs

Existing validators:

scripts/validate_business_insides_economics_ready.py

scripts/validate_ops_selection_parity.py

scripts/validate_scheduler_heartbeat.py

Ocean-drop parity/drift validators (already present in system).

Existing orchestrators (if present): scripts/run_h5_proving_day.py, scripts/system_doctor.py.

Outputs

New runner:

scripts/run_operate_day.py (NEW)

Daily artifacts:

exports/daily/<AS_OF>/operate_day_manifest.json

exports/daily/<AS_OF>/operate_day_manifest.md

exports/daily/<AS_OF>/exceptions.json (standardized)

Validation transcript:

exports/validation/board_operate_day_runner_<DATE>/full_gates_green_final.md

Definition of Done
Accepted as done only when:

scripts/run_operate_day.py --as-of <YYYY-MM-DD> --strict:

produces the manifest json+md,

exits non-zero on any red validator,

is idempotent (same inputs → same manifest content excluding timestamps).

Manifest includes exact paths to:

economics report,

po proposals,

capital protection report,

selection parity report,

scheduler heartbeat report.

Validation/Gates

Unit tests:

tests/test_run_operate_day_manifest.py (NEW)

Integration smoke:

python3 scripts/run_operate_day.py --as-of 2026-02-26 --strict

Mandatory baseline gates (same as R3).

Rollback / Backout

Revert runner; existing validators remain.

Stop-the-line

Runner returns GREEN while any required validator is skipped or missing its expected output artifact.

R4 — Proving Streak (14 consecutive GREEN operate days)

Goal (measurable)

Achieve 14 consecutive days where run_operate_day.py is GREEN and artifacts are produced.

Inputs

exports/daily/<AS_OF>/operate_day_manifest.json for each day.

Outputs

New validator:

scripts/validate_operate_streak.py (NEW)

Streak artifact:

exports/validation/operate_streak/<AS_OF>/streak_report.json

exports/validation/operate_streak/<AS_OF>/streak_report.md

Definition of Done
Accepted as done only when:

python3 scripts/validate_operate_streak.py --as-of <AS_OF> --days 14 --strict PASS.

Report lists missing/broken days explicitly.

Validation/Gates

Unit tests:

tests/test_validate_operate_streak.py (NEW)

Mandatory baseline gates (same as R3).

Rollback / Backout

N/A (read-only validator).

Stop-the-line

Any attempt to mark “operate mode stable” without a passing streak report.

R5 — PO Sign-Off Pack (decision-grade, human-minimal)

Goal (measurable)

Produce a single PO decision pack per operate day that is reviewable in <10 minutes and safe by default.

Inputs

exports/po/<AS_OF>/po_proposals.json

exports/validation/po_capital_protection/<AS_OF>/capital_protection_report.json

BUSINESS_INSIDES economics readiness report for same as_of.

Outputs

New builder:

scripts/build_po_signoff_pack.py (NEW)

Pack artifacts:

exports/po/<AS_OF>/po_signoff_pack.json

exports/po/<AS_OF>/po_signoff_pack.md

exports/po/<AS_OF>/po_signoff_pack_oracle_primary.md (oracle pack pointer only, built by zipper flow)

Definition of Done
Accepted as done only when:

Sign-off pack includes, for every recommended line:

ROIC, capital_at_risk, new_sku_cap status, exit horizon (already required),

explicit “why recommended” and “why blocked” fields,

links to underlying validator artifacts.

Pack is generated by run_operate_day.py when GREEN.

Validation/Gates

Unit tests:

tests/test_po_signoff_pack.py (NEW)

Mandatory baseline gates (same as R3).

Rollback / Backout

N/A (read-only artifacts).

Stop-the-line

Any PO sign-off pack generated without capital protection PASS.

R6 — Execution Engine (Write Canary Ladder, staged)

Goal (measurable)

Enable bounded, reversible writes (DB-first), with explicit apply gating and rollback artifacts.

Inputs

Existing write canary framework/runbooks (from prior boards).

DB backup conventions.

Outputs

Ladder doc:

docs/ops/WRITE_CANARY_LADDER_V1.md (NEW)

Stage 1 (DB-only) canaries:

scripts/run_write_canary_po_decisions.py (NEW)

DB ledger table (append-only) + migration script (if needed)

Apply manifests:

exports/apply_manifests/<timestamp>_po_decisions.json

Definition of Done
Accepted as done only when:

Stage 1 canary runs in dry-run by default and requires:

--apply AND ENABLE_* env gate AND creates DB backup AND writes apply manifest.

Post-apply validator proves DB state is consistent and can be rolled back.

Validation/Gates

Canary unit tests + apply-mode integration test using a temp DB.

Mandatory baseline gates (same as R3).

Rollback / Backout

Restore the exact pre-apply DB backup recorded in manifest.

git revert <sha> (no force reset), then rerun strict gates.

Stop-the-line

Any write without backup + manifest + explicit env gate.

Any canary that cannot be rolled back deterministically.

If attachments are missing (assumptions policy)

Missing external reference / ocean-drop files → do not “best-effort.” Mark day RED, keep last known-good anchored snapshot, and emit an exception explaining what is missing.

Missing BUSINESS_INSIDES snapshot JSON for as_of → validator must fail closed (no economics publication).

Conflicting truth sources → obey the single-truth ladder:

docs/inventory/Master_Inventory_Rules_v8.md

protocol/active/PO_making_logic_v2.md

DB operational truth

exports/dashboards derived only