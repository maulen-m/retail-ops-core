Risks + likely regressions to watch

False confidence from “green tooling” without “green streak”: the system is only end‑state when green‑streak >=14 consecutive days (explicitly required). 

012741_TASK-403_board-v9-system…

Artifact date anchoring / timezone edges: V10 notes strict artifacts anchored to the latest “complete daily-report date” while promotion date may differ; date handling can cause spurious red/green if not standardized (needs explicit contract in the next phase). 

034258_TASK-404_board-v10-endga…

Docs contamination regressions: active-scope lint must keep “archived” docs out of authority; any new docs must be added to docs/authority/INDEX.md or they risk becoming shadow-authority. 

012741_TASK-403_board-v9-system…

Write paths remain the highest capital-risk surface: the system is deliberately “no uncontrolled writes”; moving toward autonomy requires canaries + rollback proofs and must remain opt‑in gated. 

012741_TASK-403_board-v9-system…

Biggest unknowns (state assumptions; no questions)

Assume origin/main currently contains V9+V10 artifacts and contracts as reported (SHAs above). If any referenced files are missing on main, treat as stop‑the‑line and re‑establish via a docs+tests PR (no “best effort”).

Assume “daily autopilot exceptions” exist but do not yet have a stable schema + remediation mapping; next phases should formalize that into machine-validated contracts.

Assume production scheduling is still the main risk: deterministic runtime pinning + DB path correctness must be enforced everywhere (schedulers, manual commands, CI).

ASCII Roadmap Tree (Next Phases)

HORIZON: End-to-End Autonomy (profit growth + capital safety) [Owner: db_main] {Gate: 14-day green streak}

└─ V11: Autonomy Close-Loop Ops (streak + exceptions) [Coding Agent]
   {Primary Gate: build_green_streak_tracker --strict => streak_days>=14 AND exceptions critical=0}

   └─ V11.1: Date/Artifact Authority Hardening (as-of rules, “day complete”) [Coding Agent]
      {Gate: contract tests enforce “as-of” selection + day-complete validator}

      └─ V11.2: Exception Taxonomy + Remediation Playbooks [Coding Agent]
         {Gate: exceptions.json schema validated + every exception has owner/severity/action/evidence}

         └─ V12: Write Canary Framework (DB-only) [Coding Agent]
            {Gate: canary apply is idempotent + backup/rollback proof artifact exists}

            └─ V13: Write Canary Framework (Kaspi API state transitions) [Coding Agent]
               {Gate: no “HTTP-only” success; post-call state transition verified or stop-line}

               └─ V14: Capital Scale Autopilot (PO + cashflow publish blocks) [Coding Agent]
                  {Gate: PO/cashflow outputs blocked on red; ROIC path is doc-traceable; zero mixed-truth}

                  └─ V15: Full Production Autopilot (min human) [Coding Agent]
                     {Gate: ≥99% daily runs succeed unattended; <5% human time; exception SLA met}

# PLAN_BOARD_V11_AUTONOMY_CLOSE_LOOP_WRITE_CANARIES_2026-02-26

## Purpose
Turn the repo into an end-to-end, decision-grade, fail-closed business system that:
1) Diagnoses from any entrypoint (PO / inventory / cashflow / API / docs governance),
2) Runs daily with minimal human involvement (exceptions only),
3) Protects capital by blocking profit-impacting outputs on truth drift,
4) Introduces controlled write autonomy only via canaries + rollback proofs.

This plan assumes V9 (System Doctor + authority index) and V10 (endgame hard gates + streak tracker) are already promoted.

## Guiding Rules (Non-Negotiable)
- Fail-closed: missing/stale/invalid inputs => STOP.
- Single-truth ladder: formulas/spec docs are canonical; DB is operational truth; exports are derived.
- No “HTTP-only success”: execution APIs must verify state transitions.
- Writes are opt-in only: dry-run default; explicit env + --apply; backup first; rollback path required.
- No “yellow releases”: red critical gates => diagnostics allowed, operational use disallowed.

## If attachments are missing (Assumptions Policy)
- Proceed with best-effort reconstruction ONLY using repo truth hierarchy and existing promoted contracts.
- Any referenced file path that does not exist on origin/main is a STOP-LINE until restored via a docs+tests PR.
- Any unclear contract MUST be resolved by updating the owning doc first, then code, then tests.

---

## Phase V11-T0 — Baseline Snapshot + Scope Lock
### Goal (measurable)
Produce a decision-grade baseline snapshot from origin/main that can be reproduced on any machine:
- System Doctor strict PASS/FAIL explicitly recorded,
- domain scorecards generated,
- streak tracker artifact generated for “as-of” date.

### Inputs
- scripts/system_doctor.py
- scripts/build_domain_scorecards.py
- scripts/build_daily_ops_timings.py
- scripts/build_green_streak_tracker.py
- docs/authority/INDEX.md
- exports/* artifact contracts from prior boards

### Outputs (exact paths)
- exports/diagnostics/<YYYY-MM-DD>/system_health.json|.md
- exports/daily/<YYYY-MM-DD>/*_scorecard.json (PO/inventory/cashflow/truth drift)
- exports/perf/<YYYY-MM-DD>/daily_ops_timings.json|.md
- exports/health/streak/<YYYY-MM-DD>/green_streak.json|.md
- exports/validation/board_v11_<YYYY-MM-DD>/V11-T0_baseline/ (evidence markdown)

### Definition of Done
Accepted as done only when:
- all artifacts above exist for the same as-of day,
- System Doctor exit code matches strict mode expectations,
- evidence markdown lists exact commands + exit codes + output paths.

### Validation/Gates
- python3 scripts/system_doctor.py --strict --project-root <REPO_PATH>
- python3 scripts/build_domain_scorecards.py --strict --project-root <REPO_PATH> --as-of <AS_OF_DATE>
- python3 scripts/build_daily_ops_timings.py --strict --project-root <REPO_PATH> --as-of <AS_OF_DATE>
- python3 scripts/build_green_streak_tracker.py --strict --project-root <REPO_PATH> --as-of <AS_OF_DATE>
- Full baseline gate stack (see V11-PROMOTE)

### Rollback / Backout
- git revert (no writes allowed in this phase)

### Stop-the-line Criteria
- Any artifact missing or non-deterministic between two runs on same inputs
- Any “PASS” reported while strict exit code is non-zero (false-green)
- Any “as-of” date ambiguity causing mismatched directories

---

## Phase V11-R1 — Date/Artifact Authority Hardening (As-Of Rules)
### Goal (measurable)
Make “which date do we evaluate” unambiguous and contract-tested:
- define “latest complete day” for daily artifacts,
- enforce consistent as-of selection across System Doctor, scorecards, streak tracker, and autopilot.

### Inputs
- scripts/system_doctor.py
- scripts/build_domain_scorecards.py
- scripts/build_green_streak_tracker.py
- existing daily report artifacts under exports/daily/

### Outputs (exact paths)
- docs/ops/AS_OF_DATE_AUTHORITY_CONTRACT.md (new)
- scripts/resolve_as_of_date.py (new, pure function CLI)
- tests/test_as_of_date_authority_contract.py (new)
- Update System Doctor + builders to consume resolve_as_of_date() in strict mode

### Definition of Done
Accepted as done only when:
- a single authoritative “as-of” date is computed deterministically,
- all strict commands agree on output roots for the same run,
- contract test fails if any script diverges.

### Validation/Gates
- Targeted pytest for new authority logic
- python3 scripts/system_doctor.py --strict
- Full baseline gate stack

### Rollback / Backout
- git revert

### Stop-the-line Criteria
- Any strict artifact produced under the “wrong” day
- Any tool uses local timezone implicitly without documented rule

---

## Phase V11-R2 — Exception Taxonomy + Remediation Playbooks
### Goal (measurable)
Turn exceptions into actionable, machine-validated work items:
- every exception has: id, domain, severity, owner, recommended_action, evidence_paths,
- “critical” exceptions block publish/decision outputs.

### Inputs
- exports/exceptions/<YYYY-MM-DD>/exceptions.json (existing)
- scripts/run_daily_autopilot.py (existing)
- System Doctor outputs

### Outputs (exact paths)
- docs/ops/EXCEPTIONS_SCHEMA_CONTRACT.md (new)
- scripts/validate_exceptions_schema.py (new)
- scripts/normalize_exceptions.py (new or integrated into autopilot)
- tests/test_exceptions_schema_contract.py (new)
- exports/exceptions/<YYYY-MM-DD>/exceptions.md (human-readable, deterministic)

### Definition of Done
Accepted as done only when:
- validator fails closed on any malformed exception,
- critical exceptions are explicitly counted and surfaced in System Doctor + weekly scorecard,
- a “known remediation” mapping exists for top recurring exception types.

### Validation/Gates
- python3 scripts/run_daily_autopilot.py --strict --project-root <REPO_PATH> --as-of <AS_OF_DATE>
- python3 scripts/validate_exceptions_schema.py exports/exceptions/<AS_OF_DATE>/exceptions.json --strict
- python3 scripts/system_doctor.py --strict
- Full baseline gate stack

### Rollback / Backout
- git revert
- no writes beyond exports/ artifacts

### Stop-the-line Criteria
- exceptions exist only in logs but not in artifacts
- any path “catches and continues” on critical exceptions

---

## Phase V12 — Write Canary Framework (DB-only; no production writes)
### Goal (measurable)
Prove we can execute DB apply paths safely via canary:
- snapshot DB -> apply subset -> generate diff -> rollback proof,
- canary is idempotent (run twice yields same state).

### Inputs
- docs/WRITE_SIDE_GATING_CONTRACT.md + write gating manifest (existing from earlier boards)
- DB apply scripts (migrations, sync scripts) — canary only
- db/app.db (read-only input)

### Outputs (exact paths)
- docs/ops/WRITE_CANARY_RUNBOOK_V2.md (new)
- scripts/run_write_canary.py (new)
- exports/canary/<YYYY-MM-DD>/write_canary_report.json|.md
- exports/canary/<YYYY-MM-DD>/db_diff_summary.json|.md
- tests/test_write_canary_contract.py (new)

### Definition of Done
Accepted as done only when:
- canary run produces backup path + diff summary + explicit rollback command,
- idempotence test passes,
- write gating prevents accidental production apply.

### Validation/Gates
- Targeted pytest for canary contract
- Full baseline gate stack
- Explicit check: no production DB modified during tests (hash before/after)

### Rollback / Backout
- git revert
- restore canary DB from backup (proof artifact required)

### Stop-the-line Criteria
- any write occurs without explicit canary target + backup
- any apply path is non-idempotent without being classified + blocked

---

## Phase V13 — Write Canary Framework (Kaspi API; strict state transitions)
### Goal (measurable)
Eliminate “HTTP success only” for assemble/ship:
- every write-like API action has a follow-up status verification,
- failures produce explicit exceptions with order IDs and evidence.

### Inputs
- core/integrations/kaspi_api_client.py
- scripts that call assemble/ship/waybill fetch flows
- existing contract tests for waybill + state transition

### Outputs (exact paths)
- docs/ops/KASPI_API_STATE_TRANSITION_CONTRACT.md (new)
- scripts/validate_kaspi_state_transition.py (new)
- tests/test_kaspi_state_transition_contract.py (new, mocked)
- exports/exceptions/<YYYY-MM-DD>/api_state_transition_exceptions.json (if any)

### Definition of Done
Accepted as done only when:
- tests fail if code treats HTTP 2xx/204 as success without confirmed state change,
- strict mode exits non-zero on any unconfirmed transition,
- no live writes executed by default (dry-run unless explicitly allowed).

### Validation/Gates
- Targeted pytest + full baseline gate stack
- System Doctor must surface state-transition failures as critical exceptions

### Rollback / Backout
- git revert
- no live API writes allowed in this phase

### Stop-the-line Criteria
- any “write-like” API call can run without explicit gating env + confirmation
- any silent retry loop without bounded limits + surfaced exception

---

## Phase V11-PROMOTE — Promotion + Evidence + Oracle Pack
### Goal (measurable)
Promote V11 with decision-grade proof and zero ambiguity.

### Outputs (exact paths)
- docs/PLAN_BOARD_V11_AUTONOMY_CLOSE_LOOP_WRITE_CANARIES_2026-02-26.md (this file)
- docs/OPS_ROLLOUT_EVIDENCE_BOARD_V11_AUTONOMY_CLOSE_LOOP_WRITE_CANARIES_2026-02-26.md
- exports/validation/board_v11_<YYYY-MM-DD>/full_gates_green_final.md
- Oracle pack (offline): ~/Docs/Oracle/Autonomous_business/<YYYY-MM-DD>/<TASK>_board-v11_*.md

### Definition of Done
Accepted as done only when:
- evidence doc includes PR link(s), merge SHA(s), rollback steps, and artifact paths
- full gate transcript exists and is referenced
- no TODO/TBD placeholders in plan/evidence docs

### Validation/Gates (must all pass)
- python3 scripts/validate_params.py --strict
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
- python3 scripts/run_contract_suite.py --fixture small
- python3 scripts/validate_single_truth_system.py
- bash scripts/lint_docs.sh
- bash scripts/check_no_db_tracked.sh
- Scheduler validate-only + anchor health + ops status (if applicable)
- python3 scripts/system_doctor.py --strict

### Rollback / Backout
- git revert -m 1 <merge_sha>
- Restore canary DB from backup if any canary path executed

### Stop-the-line Criteria
- any gate skipped
- any evidence missing
- any write executed without canary targeting and rollback proof