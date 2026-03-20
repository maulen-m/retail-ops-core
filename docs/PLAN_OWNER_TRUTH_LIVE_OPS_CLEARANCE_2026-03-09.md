PLAN_OWNER_TRUTH_LIVE_OPS_CLEARANCE_2026-03-09
Purpose

Clear the remaining live operational blocker on top of the already-cleared truth baseline for codex/TASK-webui-owner-truth-operationalization-v1, without reopening WebUI source work, without introducing replay fallback into live mode, and without bundling new truth-side DB repair unless a new evidence packet proves a fresh truth defect.

Execution posture:

single-agent

sequential

fail-closed

one worktree / branch only

human involvement limited to login / secret refresh only if store-auth root cause is explicitly proven

Baseline assumptions:

preferred head: 25b5c1425e7b4a8164b29104362690b4fddbbef7

fallback head if READCHECK disproves preferred head: 551e2ce7278d55de398af76273c7ab244a4a8078

baseline release commit: 86ce447782a005c47ac3d1b61dde8414900320a8

rollback anchor: exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md

truth-blocker-clearance commit IDs were not provided; treat that delta as worktree-local unless READCHECK proves otherwise

no new WebUI scrape

no source remediation

no replay-only fallback in live mode

Evidence root for this phase:

exports/validation/owner_truth_live_ops_clearance/2026-03-09/

Global non-negotiables:

Live mode must not consume replay-only artifacts.

No manual creation/copying of daily_ops_report.json.

No DB write in this plan unless a new, separately justified truth-defect packet is produced first.

Any unexpected write requirement halts this plan and spins out into a separate write-gated plan.

Do not claim completion unless all listed gates are green.

Phase L0 — State Freeze + Checkpoint
Goal (measurable)

Freeze the exact starting state so the current truth-blocker-clearance delta cannot be lost or mixed with the next phase.

Inputs (files/systems)

current worktree codex/TASK-webui-owner-truth-operationalization-v1

docs/PLAN_OWNER_TRUTH_OPERATIONALIZATION_2026-03-09.md

docs/PLAN_OWNER_TRUTH_TRUTH_BLOCKER_CLEARANCE_2026-03-09.md

exports/validation/owner_truth_operationalization/2026-03-09/truth_blocker_clearance/summary.md

exports/validation/owner_truth_operationalization/2026-03-09/truth_blocker_clearance/db_write_log.md

exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md

Outputs (artifacts + exact paths)

exports/validation/owner_truth_live_ops_clearance/2026-03-09/readcheck.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/worktree_status.txt

exports/validation/owner_truth_live_ops_clearance/2026-03-09/assumptions.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/worktree_checkpoint.patch

exports/validation/owner_truth_live_ops_clearance/2026-03-09/checkpoint_decision.md

Definition of Done

Accepted as done only when:

exact head is recorded

dirty/clean state is recorded

rollback anchor is recorded

if the tree is dirty, either:

a narrow checkpoint commit is created for the existing delta, or

a patch artifact exists and is referenced as the rollback/checkpoint vehicle

Validation / Gates

git rev-parse HEAD

git status --short

bash scripts/check_no_db_tracked.sh

bash scripts/lint_docs.sh

Rollback / backout strategy

revert or drop L0 docs/patch only

no code or DB changes in L0

Stop-the-line criteria

head is not 25b5... or explicit fallback 551e2... and that discrepancy is unexplained

rollback anchor missing

any tracked/staged .db file appears

Phase L1 — Live Daily-Ops Root Cause Isolation
Goal (measurable)

Classify the exact live blocker for STOREB, ACMEWEAR, and UNIVERSAL inside run_kaspi_daily_ops and prove whether the failure is credentials, shipment/waybill state, API response semantics, or daily-artifact generation plumbing.

Inputs (files/systems)

scripts/run_owner_truth_daily.py

scripts/run_kaspi_daily_ops.py

docs/validation/OWNER_TRUTH_RUNTIME_MODE_CONTRACT.md

exports/validation/owner_truth_operationalization/2026-03-09/live_proving/blocked_inputs.json

exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_run_transcript.md

.env / anchor bootstrap outputs

scheduler validate-only outputs

Outputs (artifacts + exact paths)

exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/store_blockers.json

exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/store_blockers.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/live_ops_transcript.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/root_cause/root_cause_decision.md

tests/test_run_kaspi_daily_ops_contract.py

tests/test_live_daily_ops_store_blockers.py

Definition of Done

Accepted as done only when:

each red store is assigned an explicit blocker class

the blocker class is reproducible from captured evidence

if the blocker is credentials/secrets only, the pack explicitly says so and no speculative code edits are made

if stores go green, the blocker report records GREEN with exact evidence

Validation / Gates

targeted pytest for newly added/updated daily-ops tests

one direct reproduction run for the failing live path

one repeat run proving either:

stable same blocker class, or

green result

Rollback / backout strategy

revert code/tests/docs from L1

no DB writes permitted

Stop-the-line criteria

any “fix” that suppresses store errors without classifying them

any replay artifact introduced into live mode

any weakening of workbook-anchor enforcement

Phase L2 — Daily Artifact Contract Closure
Goal (measurable)

Guarantee that a successful live current-day run generates exports/daily/2026-03-09/daily_ops_report.json and that the validator accepts it.

Inputs (files/systems)

scripts/run_owner_truth_daily.py

scripts/generate_daily_ops_report.py

scripts/validate_daily_ops_report.py

L1 root-cause findings

runtime-mode contract

Outputs (artifacts + exact paths)

docs/validation/OWNER_TRUTH_LIVE_DAILY_ARTIFACT_CONTRACT.md

updated scripts/run_owner_truth_daily.py

updated scripts/generate_daily_ops_report.py

updated scripts/validate_daily_ops_report.py

tests/test_generate_daily_ops_report_contract.py

tests/test_validate_daily_ops_report_contract.py

exports/daily/2026-03-09/daily_ops_report.json

exports/daily/2026-03-09/daily_ops_report.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/daily_artifact_contract_report.json

Definition of Done

Accepted as done only when:

live mode produces daily_ops_report.json from live inputs

validate_daily_ops_report.py --strict passes on that file

no manual artifact copy or replay artifact injection is used

Validation / Gates

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_run_owner_truth_daily_contract.py tests/test_system_doctor_contract.py tests/test_generate_daily_ops_report_contract.py tests/test_validate_daily_ops_report_contract.py

python3 scripts/validate_daily_ops_report.py --strict --path exports/daily/2026-03-09/daily_ops_report.json

Rollback / backout strategy

revert script/test/contract changes

delete generated daily artifacts from this phase if contract is not green

Stop-the-line criteria

any manual pre-seeding of daily_ops_report.json

any use of replay summary/seed in live mode

any contract change that downgrades live fail-closed behavior

Phase L3 — Full Live Green Proving
Goal (measurable)

Turn the remaining blocked evidence into a fully green live proof for 2026-03-09.

Inputs (files/systems)

L1 and L2 outputs

scripts/run_owner_truth_daily.py

scripts/system_doctor.py

scripts/ops_status.py

current anchor/bootstrap setup

Outputs (artifacts + exact paths)

exports/validation/owner_truth_live_ops_clearance/2026-03-09/live_green/live_run_summary.json

exports/validation/owner_truth_live_ops_clearance/2026-03-09/live_green/live_run_transcript.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/live_green/live_idempotence_report.json

exports/validation/owner_truth_live_ops_clearance/2026-03-09/live_green/system_doctor_after_green.txt

docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_LIVE_GREEN_2026-03-09.md

Definition of Done

Accepted as done only when:

./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict exits 0

./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09 is GREEN

a second live rerun is semantically identical except approved volatile keys

no new truth blocker is introduced

Validation / Gates

./.venv/bin/python scripts/ops_status.py --project-root .

./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict

./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09

targeted pytest set from L1/L2

Rollback / backout strategy

revert code changes if live proof regresses

if any unexpected write was introduced, restore latest DB backup and rerun truth gates before any new attempt

Stop-the-line criteria

one green live run followed by a red rerun

any hidden manual artifact needed between runs

any new truth drift requiring write-side correction

Phase L4 — Merge / Release / Oracle Refresh
Goal (measurable)

Convert the branch from blocked evidence into merge-ready release documentation only after L3 is fully green.

Inputs (files/systems)

L3 live-green evidence

current merge manifest

release anchor

oracle pack structure

Outputs (artifacts + exact paths)

exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json

exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md

exports/validation/owner_truth_release/2026-03-09/full_gates_green_live_ops.md

Oracle_listings/packs/owner_truth_live_green_2026-03-09/PACK_SUMMARY.md

Oracle_listings/packs/owner_truth_live_green_2026-03-09/bundle.md

Oracle_listings/packs/owner_truth_live_green_2026-03-09/oracle_files_manifest.txt

Oracle_listings/packs/owner_truth_live_green_2026-03-09/ArchiveSales_ALL_STORES_statusdate_mapped.csv

Definition of Done

Accepted as done only when:

merge manifest status is GREEN

exact commits, exact commands, exact rollback, and scope-out are documented

oracle pack contains ArchiveSales_ALL_STORES_statusdate_mapped.csv

oracle pack does not substitute ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv

Validation / Gates

bash scripts/lint_docs.sh

bash scripts/check_no_db_tracked.sh

python3 scripts/check_release_hygiene.py --strict --project-root .

manifest content checks on the oracle pack

Rollback / backout strategy

revert merge/release/oracle docs only

preserve live-green evidence

Stop-the-line criteria

merge manifest still says DEFER

wrong CSV is packed

rollback mapping is missing

Phase L5 — Automation Hardening
Goal (measurable)

Make the same class of live blocker immediately diagnosable in future current-day runs.

Inputs (files/systems)

docs/DAILY_SOP.md

docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md

L1 blocker taxonomy

L3 live-green evidence

Outputs (artifacts + exact paths)

updated docs/DAILY_SOP.md

updated docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md

exports/validation/owner_truth_live_ops_clearance/2026-03-09/automation_hardening_report.md

tests/test_kaspi_daily_ops_failure_classification.py (if code-level classification is added)

Definition of Done

Accepted as done only when:

operator docs point to exact live blocker classes

scheduler/runtime docs remain consistent with live-vs-replay contract

hardening does not weaken fail-closed behavior

Validation / Gates

bash scripts/lint_docs.sh

bash scripts/install_single_truth_ops_scheduler.sh --validate-only

relevant targeted pytest

Rollback / backout strategy

revert docs/tests/scripts from L5

Stop-the-line criteria

docs contradict runtime-mode contract

scheduler docs drift from the actual validate-only contract

Phase L6 — Deferred Scale Queue Lock
Goal (measurable)

Keep scale work visible but out of the live-ops-clearance branch.

Inputs (files/systems)

existing operationalization backlog

current merge manifest

live-green evidence or blocker pack

Outputs (artifacts + exact paths)

exports/validation/owner_truth_live_ops_clearance/2026-03-09/deferred_scale_backlog.md

Definition of Done

Accepted as done only when:

all scale items are explicitly marked non-merge scope

no new WebUI scrape/source remediation enters this branch

no unrelated docs/plan-cleanup work is mixed into this branch

Validation / Gates

bash scripts/lint_docs.sh

Rollback / backout strategy

revert backlog doc only

Stop-the-line criteria

source work re-enters scope

parallel worktrees are introduced without clear isolation need

If attachments are missing — assumptions policy

If no new commit IDs exist for the truth-blocker-clearance pass, treat the pass as worktree-local on top of 25b5c1425e7b4a8164b29104362690b4fddbbef7.

If 25b5... is not available locally, fail closed to 551e2ce7278d55de398af76273c7ab244a4a8078 and record the fallback in readcheck.md.

If files/exports/po_dashboard_data.json cannot be rendered due size limits, use the issue-analysis pack and truth-blocker summary as authoritative proof of restoration, but do not regenerate it just to satisfy documentation.

If live proving for 2026-03-09 cannot be completed because of real current-day operational inputs, emit a blocker pack and do not claim green.

If any new write appears necessary, stop this plan and create a separate write-gated follow-up with backup, before/after diffs, and rollback before execution.