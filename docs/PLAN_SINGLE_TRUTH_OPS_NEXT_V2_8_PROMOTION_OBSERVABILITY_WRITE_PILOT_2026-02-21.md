PLAN_SINGLE_TRUTH_OPS_NEXT_V2_8_PROMOTION_OBSERVABILITY_WRITE_PILOT_2026-02-21
Purpose

Promote the v2.7 “release/CI/write-scale” work into the long-lived production branch, then make post-merge ops decisioning nearly zero-click by standardizing on a single canonical drift-pack entrypoint and hardening write-side gating semantics—without enabling any DB writes until a minimal-blast-radius pilot is explicitly approved and fully gated.

Phase list
Phase R0 — Production Promotion + Integration Evidence

Goal (measurable):

v2.7 changes are merged into production with a recorded merge SHA and a decision-grade integration evidence note.

Inputs (files/systems):

Branch: codex/TASK-ops-rollout-v2-7-release-ci-write-scale

Key files: .github/workflows/single_truth_headless.yml, scripts/prepare_ci_headless_fixture.py, scripts/validate_write_side_gating.py, config/write_side_gating_manifest.yaml, scripts/build_single_truth_drift_pack.py, scripts/validate_params.py, docs updates.

Commits (provided): 447bc64, 6966537, 9b1f318.

Outputs (artifacts + exact paths):

docs/OPS_ROLLOUT_EVIDENCE_V2_7_INTEGRATION_<DATE>.md

claude/journal.md appended entries for promotion steps.

Definition of Done (Accepted as done only when…):

Evidence doc includes:

merge commit SHA

CI workflow run URL(s) for single_truth_headless

the exact “required gate chain” list (H1–H9) and where evidence lives

rollback instructions

Validation/Gates (silent-failure catching):

CI: single_truth_headless workflow must PASS on the merge commit.

Local: H1–H9 strict chain must be recorded in evidence packs (do not claim green unless evidence exists).

Rollback / backout:

Revert merge commit; or git revert 9b1f318 6966537 447bc64 (order newest→oldest).

Stop-the-line criteria:

CI passes but local strict chain fails (or vice versa).

Any evidence file referenced is missing or contradictory.

Phase R1 — Post-merge Observation Window (read-only)

Goal (measurable):

Two consecutive daily runs produce drift pack status PASS or WARN only; zero STOP_LINE.

Inputs:

Runtime scheduler jobs (existing launchd setup), plus read-only CLI entrypoints:

ops_status

check_anchor_health

drift pack builder

Outputs:

exports/validation/daily/<YYYY-MM-DD>/single_truth_drift_pack.md

exports/validation/daily/<YYYY-MM-DD>/single_truth_drift_pack.json

Evidence references appended to docs/OPS_ROLLOUT_EVIDENCE_V2_7_INTEGRATION_<DATE>.md

Definition of Done:

Two-day drift pack results recorded with statuses and reasons.

Validation/Gates:

Drift-pack determinism (same inputs => same output) must be asserted by test coverage and/or repeated-run evidence.

No DB mtime changes attributable to drift pack (read-only contract).

Rollback / backout:

If failure is operational (anchors stale, mtime skew), fix anchors/time first; do not loosen gates.

If failure is code regression, revert to pre-merge state.

Stop-the-line criteria:

Any STOP_LINE classification.

Any evidence of DB modification during read-only checks.

Phase R2 — Observability Canonicalization (one drift-pack entrypoint)

Goal (measurable):

Exactly one canonical “daily decision pack” entrypoint is documented and test-enforced; any deprecated/duplicate entrypoints are either removed or explicitly deprecated with redirects.

Inputs:

Existing docs: docs/PLAN_SINGLE_TRUTH_OPS_ROLLOUT_V2_6_OBSERVABILITY_*.md, docs/DAILY_SOP.md, docs/00_START_HERE.md, docs/SYSTEM_OVERVIEW.md

Scripts: scripts/build_single_truth_drift_pack.py (and any legacy drift-pack scripts if present).

Outputs:

docs/DAILY_SOP.md updated “Daily ops decision flow” section (canonical entrypoint only).

tests/test_ops_docs_anchor_contract.py expanded (or new test) to enforce canonical drift-pack reference.

Definition of Done:

Searching docs cannot find multiple conflicting drift-pack commands for the same purpose.

Validation/Gates:

Docs lint + doc-contract tests must fail if deprecated drift-pack entrypoint is referenced.

Rollback / backout:

Revert docs/tests changes only.

Stop-the-line criteria:

Any operator-facing doc contains conflicting “what to run daily” instructions.

Phase R3 — Write-Side Gating Hardening (runtime semantics)

Goal (measurable):

Reduce bypass risk: write gating is not only “token present” but also “behavior enforced” for highest-risk scripts.

Inputs:

config/write_side_gating_manifest.yaml

scripts/validate_write_side_gating.py

docs/WRITE_SIDE_GATING_CONTRACT.md

docs/WRITE_APPLY_RUNBOOK.md

Outputs:

A “runtime gating helper” design (can be implemented later) and a prioritized list of scripts needing semantic enforcement tests.

Add tests (design-only here) that validate: without env gate + --apply, write paths do not execute.

Definition of Done:

Plan enumerates:

Tier-1 scripts (highest capital risk) requiring runtime semantic tests

Exact tests to add, and what each test proves

Validation/Gates:

Strict chain must fail if manifest breaks.

New tests (when implemented) must fail-first and prove gating enforcement.

Rollback / backout:

Revert helper/tests; manifest contract remains.

Stop-the-line criteria:

Any discovered write-capable script not listed in the manifest.

Any script that writes without both env gate and apply flag.

Phase R4 — Safe Write/Apply Pilot (tiny blast radius; opt-in only)

Goal (measurable):

Execute exactly one low-risk write/apply workflow under full gating, with a deterministic dry-run diff, and a rollback path.

Inputs:

Candidate script from manifest (choose lowest blast radius).

docs/WRITE_APPLY_RUNBOOK.md

Outputs:

Pilot run appendix in docs/WRITE_APPLY_RUNBOOK.md:

preflight checklist

dry-run outputs location

apply command (documented, not executed in planning)

rollback steps

Definition of Done:

Runbook includes a “no surprises” checklist and explicit stop-line conditions.

Validation/Gates:

Dry-run produces deterministic diff output; apply requires explicit env+flag; backup snapshot exists.

Rollback / backout:

Restore DB backup (where applicable) + revert resulting changes using idempotent scripts.

Stop-the-line criteria:

Any missing backup.

Any mismatch between dry-run expected and planned apply effect.

Phase R5 — Scale & Policy (CI required + release train)

Goal (measurable):

CI headless gates become the default release gate for all future changes; release process is documented and low-touch.

Inputs:

.github/workflows/single_truth_headless.yml

docs/CI_HEADLESS_PLAN.md

Outputs:

docs/RELEASE_PROCESS_SINGLE_TRUTH.md (or append to SYSTEM_OVERVIEW) describing:

required checks

evidence pack expectations

rollback standard

Definition of Done:

A new engineer can follow the release process without tribal knowledge.

Validation/Gates:

Doc contract tests ensure release process doc references the same canonical gate chain.

Rollback / backout:

Docs-only rollback.

Stop-the-line criteria:

Any release step relies on machine-local absolute paths or undocumented secrets.

If attachments are missing (assumptions policy)

Treat repo state as source-of-truth.

Every assumption must be written explicitly in claude/journal.md with a timestamp.

For each assumption, define a falsification gate (test, lint, contract check) that would catch it.

Prefer failing closed over inventing behavior.