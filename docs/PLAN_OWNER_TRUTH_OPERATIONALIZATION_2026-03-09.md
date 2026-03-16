# PLAN_OWNER_TRUTH_OPERATIONALIZATION_2026-03-09

## Purpose
Take the already-green `2026-03-08` WebUI owner-truth stabilization baseline and make it portable, scheduler-safe, and live-date provable without reopening WebUI source acquisition.

Execution model:
- single-agent
- sequential
- fail-closed
- one branch/worktree only

Single-truth conflict order:
1. `docs/inventory/Master_Inventory_Rules_v8.md`
2. `docs/inventory/Sales_Data_Model_V16.md`
3. `docs/protocol/active/PO_making_logic_v2.md`
4. active validation contracts (`docs/validation/*`)
5. code/tests

Starting assumption:
- preferred start tip: `25b5c1425e7b4a8164b29104362690b4fddbbef7` if present and clean
- fallback proved tip: `551e2ce7278d55de398af76273c7ab244a4a8078`
- baseline release commit: `86ce447782a005c47ac3d1b61dde8414900320a8`
- rollback anchor: `exports/validation/owner_truth_release/2026-03-04/full_gates_green_final.md`

Evidence root for this plan:
- `exports/validation/owner_truth_operationalization/2026-03-09/`

Risks + likely regressions to watch

Anchor symlinks still resolve to machine-local workbook paths, and the proving transcript shows those local targets directly. That is accepted operationally today, but it is the next portability risk. 

KASPI_IMPORT_SCHEDULER_INCIDENT…

PO_CONTRACT

Launchd plist assets and older helper scripts remain outside the current hygiene scope and may still contain absolute paths by design. The anchored replay is durable; the installation boundary is not yet decision-grade. 

PO_CONTRACT

The current proof is anchored to 2026-03-08. The WebUI contract explicitly says frozen-pack structural integrity is not freshness, and current-day freshness must remain a separate concern. The next plan therefore should split replay mode from live mode instead of treating anchored replay as general live-ops proof. 

PO_CONTRACT

The uploaded bundle proves through 551e2ce...; the provided db_main handoff says the latest clean tip is 25b5c142.... That is likely fine, but it still needs a fresh READCHECK before any new work begins.

Biggest unknowns

Whether 25b5c142... is a pure evidence/docs commit on top of 551e2ce... or includes additional functional deltas. Assumption: it is safe and clean, as stated in db_main.

Whether a true live-date run on 2026-03-09 can remain green without replay-only seed materialization. The current contracts forbid hidden dependencies, but the proofs shown are replay proofs.

Whether the oracle pack reported in db_main (045815_TASK-000_webui-green-stabilization-oracle_pack) is repo-local or external-only. Assumption: it exists and should be preserved, but the authoritative repo-local baseline remains exports/validation/owner_truth_release/2026-03-08/full_gates_green_final.md. 

PO_CONTRACT

Whether scheduler/install assets can be made portable without increasing human setup beyond one-time secrets/login entry.

---

## Phase R0 — Baseline READCHECK + Tip Freeze

### Goal (measurable)
Freeze one verified starting tip and one verified evidence root before any code changes.

### Inputs
- provided `db_main` handoff
- `exports/validation/owner_truth_release/2026-03-08/full_gates_green_final.md`
- `exports/validation/owner_truth_release/2026-03-08/release_manifest.json`
- `exports/validation/owner_truth_release/2026-03-08/commit_manifest.json`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_GREEN_STABILIZATION_2026-03-08.md`

### Outputs (exact paths)
- `exports/validation/owner_truth_operationalization/2026-03-09/readcheck.md`
- `exports/validation/owner_truth_operationalization/2026-03-09/baseline_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/baseline_inventory.txt`
- `exports/validation/owner_truth_operationalization/2026-03-09/assumptions.md`

### Definition of Done
Accepted as done only when:
- current branch tip is verified as `25b5c142...` or explicit fallback `551e2ce...`
- working tree is clean before implementation starts
- baseline manifest records exact branch, exact head, rollback anchor, oracle-pack assumptions, and evidence roots

### Validation / Gates
- `git rev-parse HEAD`
- `git status --short`
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- docs-only revert of R0 artifacts
- no code or DB changes allowed in R0

### Stop-the-line criteria
- working tree is dirty
- current head cannot be reconciled to `25b5c142...` or `551e2ce...`
- release anchor or commit manifest is missing/unreadable

---

## Phase R1 — Runtime Mode Split (Replay vs Live)

### Goal (measurable)
Separate anchored replay from live operations so frozen `2026-03-08` proving inputs cannot silently leak into future live runs.

### Inputs
- `scripts/run_owner_truth_daily.py`
- `scripts/system_doctor.py`
- `scripts/smoke_test_owner_truth_daily.py`
- `docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
- `docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md`
- `docs/DAILY_SOP.md`

### Outputs (exact paths)
- `docs/validation/OWNER_TRUTH_RUNTIME_MODE_CONTRACT.md`
- `scripts/resolve_owner_truth_runtime_mode.py`
- updated `scripts/run_owner_truth_daily.py`
- updated `scripts/system_doctor.py`
- updated `scripts/smoke_test_owner_truth_daily.py`
- `tests/test_owner_truth_runtime_mode.py`
- updated `tests/test_run_owner_truth_daily_contract.py`
- updated `tests/test_system_doctor_contract.py`
- `exports/validation/owner_truth_operationalization/2026-03-09/runtime_mode_report.json`

### Definition of Done
Accepted as done only when:
- `replay` mode is the only mode permitted to consume frozen board-runtime seed material for `2026-03-08`
- `live` mode rejects replay-only seed materialization
- `live` mode fails closed on missing fresh prerequisites instead of silently using replay evidence

### Validation / Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_truth_runtime_mode.py tests/test_run_owner_truth_daily_contract.py tests/test_system_doctor_contract.py`
- `./.venv/bin/python scripts/smoke_test_owner_truth_daily.py --as-of 2026-03-08 --strict`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert the runtime-mode commit only
- preserve R0 baseline artifacts

### Stop-the-line criteria
- any live-mode path can still materialize replay-only artifacts
- any publication gate is weakened
- any new manual governance prerequisite is introduced

---

## Phase R2 — Scheduler + Install Asset Portability

### Goal (measurable)
Remove personal-path coupling from active scheduler/install assets while keeping fail-closed runtime behavior.

### Inputs
- `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`
- `config/com.example.kaspi-import.plist`
- `config/com.example.kaspi-waybill-deadline.plist`
- `config/com.example.kaspi-daily-ops-report.plist`
- `scripts/install_scheduler.sh`
- `scripts/install_single_truth_ops_scheduler.sh`
- `scripts/run_kaspi_import_scheduler.py`

### Outputs (exact paths)
- `config/launchd_templates/com.example.kaspi-import.plist.tmpl`
- `config/launchd_templates/com.example.kaspi-waybill-deadline.plist.tmpl`
- `config/launchd_templates/com.example.kaspi-daily-ops-report.plist.tmpl`
- `scripts/render_launchd_plists.py`
- updated `scripts/install_scheduler.sh`
- updated `scripts/install_single_truth_ops_scheduler.sh`
- `tests/test_render_launchd_plists.py`
- updated scheduler contract tests
- `exports/validation/owner_truth_operationalization/2026-03-09/scheduler_portability_report.json`

### Definition of Done
Accepted as done only when:
- committed scheduler assets are templates or repo-relative renderers, not machine-local payloads
- validate-only scheduler install works from the repo root
- scheduler contract tests still pass

### Validation / Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_render_launchd_plists.py tests/test_kaspi_import_scheduler_contract.py tests/test_kaspi_waybill_deadline_scheduler_contract.py tests/test_kaspi_daily_ops_report_scheduler_contract.py tests/test_kaspi_daily_ops_workflow_contract_doc.py`
- `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`

### Rollback / backout strategy
- revert scheduler/install portability changes
- delete generated portability artifacts

### Stop-the-line criteria
- any tracked active scheduler asset still requires manual path editing
- any runtime path becomes best-effort instead of fail-closed
- scheduler timing/test contract drifts from `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md`

---

## Phase R3 — Anchor Bootstrap + Health Contract

### Goal (measurable)
Reduce anchor setup to one deterministic bootstrap/validate path that either makes `ops_status` green or fails loudly.

### Inputs
- `config/anchors/README.md`
- `docs/DAILY_SOP.md`
- `scripts/check_anchor_health.py`
- `scripts/ops_status.py`

### Outputs (exact paths)
- `scripts/bootstrap_owner_truth_anchors.py`
- `docs/ops/OWNER_TRUTH_ANCHOR_BOOTSTRAP.md`
- `tests/test_bootstrap_owner_truth_anchors.py`
- `exports/validation/owner_truth_operationalization/2026-03-09/anchor_bootstrap_report.json`

### Definition of Done
Accepted as done only when:
- one command can bootstrap or validate CRM, inbound, and stock anchors
- missing/stale/invalid anchors return non-zero with explicit remediation text
- no silent fallback to hidden machine-local files remains in active automation

### Validation / Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_bootstrap_owner_truth_anchors.py`
- `./.venv/bin/python scripts/bootstrap_owner_truth_anchors.py --validate-only --project-root .`
- `python3 scripts/check_anchor_health.py --project-root .`
- `./.venv/bin/python scripts/ops_status.py --project-root .`

### Rollback / backout strategy
- revert bootstrap tool/docs/tests
- restore prior anchor behavior only if explicitly documented in rollback notes

### Stop-the-line criteria
- bootstrap introduces hidden dependency on manual symlink editing
- `ops_status` becomes green without verified anchors
- anchor validation is weakened or bypassed

---

## Phase R4 — Fresh-Date Live Proving

### Goal (measurable)
Prove that live operations for `2026-03-09` (or the first available date `>= 2026-03-09`) can run without replay-only scaffolding.

### Inputs
- R1–R3 outputs
- `exports/validation/owner_truth_release/2026-03-08/*`
- current repo `.venv`

### Outputs (exact paths)
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_run_summary.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_run_transcript.md`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/live_idempotence_report.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/blocked_inputs.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/live_proving/blocked_inputs.md`
- `docs/OPS_ROLLOUT_EVIDENCE_OWNER_TRUTH_LIVE_PROVING_2026-03-09.md`

### Definition of Done
Accepted as done only when:
- two strict live-mode runs are semantically stable
- no replay-only artifacts are consumed in live mode
- if live proving cannot pass, blocker artifacts exist and no green claim is made

### Validation / Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_owner_truth_runtime_mode.py tests/test_run_owner_truth_daily_contract.py tests/test_system_doctor_contract.py`
- `./.venv/bin/python scripts/run_owner_truth_daily.py --mode live --as-of 2026-03-09 --strict`
- `./.venv/bin/python scripts/system_doctor.py --strict --project-root . --as-of 2026-03-09`
- `./.venv/bin/python scripts/ops_status.py --project-root .`

### Rollback / backout strategy
- revert live-proving code changes
- preserve blocker pack if run is red
- do not overwrite `2026-03-08` release anchor

### Stop-the-line criteria
- live mode auto-fills missing fresh inputs from replay sources
- any green claim is made without green live gates
- any hidden manual artifact appears between the two live runs

---

## Phase R5 — Observability + Merge/Oracle Refresh

### Goal (measurable)
Produce a PR-ready merge pack and refresh the isolated oracle pack with the correct archive sales CSV.

### Inputs
- all prior phase outputs
- `Oracle_listings/oracle_pack_file_lists.md`
- existing stabilization oracle-pack handoff from `db_main`

### Outputs (exact paths)
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.json`
- `exports/validation/owner_truth_operationalization/2026-03-09/merge_manifest.md`
- `exports/validation/owner_truth_operationalization/2026-03-09/deferred_scale_backlog.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/PACK_SUMMARY.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/bundle.md`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/oracle_files_manifest.txt`
- `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/ArchiveSales_ALL_STORES_statusdate_mapped.csv`

### Definition of Done
Accepted as done only when:
- the oracle pack contains the exact involved files plus `ArchiveSales_ALL_STORES_statusdate_mapped.csv`
- it does **not** substitute `ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv`
- merge manifest maps exact commits, exact gates, exact rollback, and deferred backlog

### Validation / Gates
- `bash scripts/lint_docs.sh`
- `bash scripts/check_no_db_tracked.sh`
- `python3 scripts/check_release_hygiene.py --strict --project-root .`
- `grep -q 'ArchiveSales_ALL_STORES_statusdate_mapped.csv' Oracle_listings/packs/owner_truth_operationalization_2026-03-09/oracle_files_manifest.txt`
- `! grep -q 'ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv' Oracle_listings/packs/owner_truth_operationalization_2026-03-09/oracle_files_manifest.txt`

### Rollback / backout strategy
- revert merge/oracle-pack docs
- delete the refreshed oracle pack if manifest is wrong

### Stop-the-line criteria
- wrong CSV packed
- missing rollback mapping
- merge manifest claims green with any red gate

---

## Phase R6 — Deferred Scale Queue Lock

### Goal (measurable)
Keep scale work visible but out of the operationalization merge.

### Inputs
- R0–R5 outputs
- `AGENTS.md`
- `docs/DAILY_SOP.md`

### Outputs (exact paths)
- `exports/validation/owner_truth_operationalization/2026-03-09/deferred_scale_backlog.md`

### Definition of Done
Accepted as done only when:
- all deferred scale work is explicitly marked “not in merge scope”
- no source-work restart is mixed into operationalization

### Validation / Gates
- `bash scripts/lint_docs.sh`

### Rollback / backout strategy
- revert backlog doc only

### Stop-the-line criteria
- any new WebUI scrape/source restart enters this branch
- multi-worktree parallelism is introduced without isolation need

---

## If attachments are missing — assumptions policy
- If `25b5c1425e7b4a8164b29104362690b4fddbbef7` is not available locally, fail closed to `551e2ce7278d55de398af76273c7ab244a4a8078` and record that fallback in `readcheck.md`.
- If the external stabilization oracle pack is missing, preserve the repo-local `2026-03-08` release anchor as authoritative and regenerate only the refreshed oracle pack under `Oracle_listings/packs/owner_truth_operationalization_2026-03-09/`.
- If `2026-03-09` live inputs are unavailable, emit `blocked_inputs.{json,md}` and do not claim green.
- If any source conflicts, prefer the most recent active validation contract or release evidence doc, then update code/tests only after the contract is explicit.