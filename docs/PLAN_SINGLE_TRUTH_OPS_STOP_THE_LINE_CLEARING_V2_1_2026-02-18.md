Repo: ~/Docs/Autonomous_business
Execution model: single‑take by db_main agent (optional 1 additional QA agent only after code is ready)
Ads: explicitly excluded
Status: Stop‑the‑line currently triggered (per human evidence)

0) Context and what changed (already shipped)
Shipped in Ops Reliability v2.1 “Critical5” (already in repo)

Commits (as provided):

a9b0fb9 tests: add critical5 coverage for preflight env, venv pinning, oracle comparator chain

a974041 ops: pin strict preflight runtime and tighten workbook freshness guards

e6da994 oracle: include workbook anchor comparator chain in primary pack contract

6fd4c74 docs: align ops reliability v2.1 controls and incident follow-up

Key behavioral implications:

Workbook gate tightened: default max_age_hours=36 and future mtime skew rejected (default 120s).

Runtime pinning attempt: strict preflight now intends to re-exec into repo .venv/bin/python when present.

Scheduler env contract: launchd plist sets workbook thresholds and workbook path.

Current stop-the-line evidence (human run, 2026-02-18)

Scheduler installed; manual launchctl start ... worked.

Stop‑the‑line triggered because:

Strict preflight fail‑closed: workbook stale (age_hours=52.7, max=36.0).

Launchd runtime mismatch: logs show missing pandas/requests in some runs (interpreter/deps drift).

Interpretation:

The workbook freshness gate is doing its job (catching a real ops gap).

The interpreter drift is not acceptable because it can silently break strict enforcement and/or alerting.

1) Objective

Clear stop‑the‑line safely by eliminating the two failure classes:

Workbook anchor freshness failure becomes an actionable ops routine (human updates workbook before the run) with zero ambiguity about “which workbook” is canonical.

Launchd runtime determinism becomes fail‑closed and reproducible: scheduled jobs must run with the same interpreter + deps as tests (repo .venv), not a PATH-selected python.

Constraints (non‑negotiable):

Fail‑closed remains: no loosening gates to “get green.”

No write‑side DB actions in this plan (unless separately gated with explicit env var + --apply, but default is none).

No ads worktree changes.

2) Root-cause hypotheses (decision-grade, no questions)
A) Workbook stale

Most likely cause: the symlink points at a workbook copy that simply wasn’t updated within 36h (your human evidence shows 52.7h).
Second-order risk: any stale alternate-workspace anchor examples increase the probability of updating the wrong file.
Canonical authority for anchor paths is `config/anchors/README.md`.

B) Launchd runtime mismatch (missing pandas/requests)

Most likely cause: the plist still uses /usr/bin/env python3 (PATH‑dependent), so launchd can choose an interpreter without the repo deps. The current contract test locks that behavior in unless changed.

Also likely: strict preflight’s “re-exec into .venv” can be defeated if any import requiring third-party deps occurs before the re-exec executes. This creates the exact failure mode you saw: ImportError before bootstrap, so no self-heal.

Decision: we will not “trust bootstrap alone.” We will pin launchd to .venv/bin/python directly and also make bootstrap execute before any non‑stdlib imports as a safety net.

3) Locked decisions

Launchd runs .venv/bin/python (not /usr/bin/env python3).

WorkingDirectory in plists must be repo root (so relative paths are stable).

Workbook canonical location becomes single-truth (recommended: <REPO_PATH>/excel_ui/SALES_KSP_CRM_V3.xlsx, with anchors symlinked to it).

Workbook max-age default stays 36h (capital protection).

Stop-the-line remains active until both: workbook freshness pass + launchd interpreter pass.

4) Phase plan (single-take execution by db_main)
Phase 0 — Baseline capture and “why it fails” evidence (db_main)

Goal: produce a short evidence pack that proves the two failure modes clearly and reproducibly.

Actions:

Capture:

current plist contents for both jobs

current sys.executable used by a launchd-triggered run (extract from logs or add a temporary diagnostic print if needed)

workbook path + mtime + age_hours calculation output

Write evidence to:
exports/validation/ops_stop_the_line_clear_2026-02-18/baseline.md

Acceptance:

Evidence clearly shows:

workbook stale failure is from a specific file path

python mismatch is from launchd selecting a non-venv interpreter and failing on imports (or at least proves interpreter != .venv/bin/python)

Phase 1 — Fix launchd interpreter determinism (db_main)

Goal: launchd must run with repo .venv, and must fail closed with a clear error if .venv is missing or broken.

Implementation intent (planning spec, not code here):

Update:

config/com.example.single-truth-preflight.plist

config/com.example.on-delivery-residuals.plist

ProgramArguments should use:

.venv/bin/python (or absolute <REPO_PATH>/.venv/bin/python)

script path (scripts/...py)

Ensure:

WorkingDirectory is <REPO_PATH>

environment contains the workbook thresholds (already does)

Update contract tests accordingly:

tests/test_single_truth_ops_scheduler_contract.py

assert .venv/bin/python (or absolute venv path) is used

remove assertions for /usr/bin/env + python3

Harden installer to be fail-closed:

scripts/install_single_truth_ops_scheduler.sh must:

verify .venv/bin/python exists

verify .venv/bin/python -c "import pandas, requests" succeeds

refuse to install/load jobs if checks fail (clear remediation message)

Artifacts:

updated plists

updated installer

updated tests

evidence file showing expected ProgramArguments + venv import checks

Acceptance:

A “simulated launchd run” using the same ProgramArguments succeeds locally with .venv.

No PATH reliance remains.

Phase 2 — Make preflight bootstrap truly early (db_main)

Goal: even if a human runs preflight with the wrong python, it self-corrects before any internal imports can crash.

Implementation intent:

In scripts/run_strict_daily_preflight.py:

move the bootstrap check to execute before any core.* imports

ensure “already in venv” is a no-op

Extend tests:

add a subprocess-based test that proves: if the current python cannot import requests, the script still re-execs into .venv and proceeds.

Acceptance:

Repro test demonstrates early bootstrap prevents “ImportError before re-exec”.

Phase 3 — Canonicalize workbook anchor path and reduce ambiguity (db_main + Human)

Goal: eliminate “updated the wrong workbook” and make stale-workbook resolution a 60-second task.

db_main changes (docs + helper tooling, no data writes):

Update:

config/anchors/README.md

docs/DAILY_SOP.md

Replace legacy alternate-workspace anchor examples with a canonical single location:

Recommended canonical workbook: <REPO_PATH>/excel_ui/SALES_KSP_CRM_V3.xlsx

Anchor symlink should point to that:

<REPO_PATH>/config/anchors/SALES_KSP_CRM_LATEST.xlsx -> <REPO_PATH>/excel_ui/SALES_KSP_CRM_V3.xlsx

Optional (high leverage, low risk):

Add scripts/check_workbook_anchor.py:

prints: resolved path, mtime, age_hours, future-skew status

exit code nonzero if stale or in future

used by humans before smoke start

Human critical action (≤10%):

Update the actual workbook file (the shipping journal export) so it is truly current, then re-point symlink if needed.

Rerun scripts/check_workbook_anchor.py (or equivalent) until it passes.

Acceptance:

workbook freshness passes with age_hours < 36

workbook path is unambiguous and “single canonical workbook” is documented

Phase 4 — Smoke run and clear stop-the-line (Human, optionally assisted by QA agent)

Human steps (copy/paste only):

./scripts/install_single_truth_ops_scheduler.sh

launchctl start com.example.single-truth-preflight

launchctl start com.example.on-delivery-residuals

Save logs + lineage artifact evidence to:
exports/validation/ops_stop_the_line_clear_2026-02-18/smoke.md

Stop‑the‑line clear criteria:

Strict preflight PASS with fresh workbook

Logs show interpreter is .venv/bin/python

No ImportError for pandas/requests

Lineage file emitted (if configured) and includes exit_code=0

5) Validation gates (must be green before asking human to smoke)
Targeted suite (new/updated tests)

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q targeting:

scheduler contract tests

preflight python pinning tests

(optional) workbook helper tests

Full gate chain (existing non-negotiables)

python3 scripts/validate_params.py --strict

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q

python3 scripts/run_contract_suite.py --fixture small

python3 scripts/validate_single_truth_system.py

scripts/lint_docs.sh

scripts/check_no_db_tracked.sh

6) Rollback (fail-closed and fast)

Code rollback:

git revert <new_commits_in_reverse_order>

Scheduler rollback:

launchctl unload ~/Library/LaunchAgents/com.example.single-truth-preflight.plist

launchctl unload ~/Library/LaunchAgents/com.example.on-delivery-residuals.plist

rerun installer from the reverted repo state

No DB rollback expected (this plan introduces no --apply actions).

7) Deliverables checklist (db_main must produce)

 Updated plists pinning .venv/bin/python

 Updated installer with venv + import checks (fail closed)

 Updated run_strict_daily_preflight.py to bootstrap before internal imports

 Updated contract tests + new subprocess test

 Updated docs/DAILY_SOP.md + config/anchors/README.md canonical workbook guidance

 Evidence pack folder under exports/validation/ops_stop_the_line_clear_2026-02-18/:

baseline.md

targeted_tests_red_then_green.md (fail-first evidence)

full_gates_green.md

smoke.md (human)
