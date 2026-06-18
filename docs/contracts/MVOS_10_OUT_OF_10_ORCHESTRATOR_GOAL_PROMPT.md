# MVOS 10/10 Orchestrator Goal Prompt

Status: `READY_FOR_COPY_PASTE_TO_ORCHESTRATOR_AGENT`

Created: `2026-05-18`

Canonical contract:

`~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md`

Starter pack:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS`

Use the following prompt as one copy-paste block for the main orchestrator agent.

```text
/GOAL Implement the MVOS 10/10 Decision-Grade Acceptance Contract for ~/Docs/Autonomous_business until the repo reaches a verifiable 10/10 decision-grade state for the declared operating scope, or stops at a hard RED stopline.

PRIMARY OBJECTIVE

Turn the Autonomous_business repo into a decision-grade operating system that satisfies the reviewed MVOS 10/10 Acceptance Contract.

The final outcome must be verifiable by artifacts, validators, and gates, not by narrative.

STARTING AUTHORITY

Read first, in order:

1. ~/Docs/Autonomous_business/AGENTS.md
2. ~/Docs/Autonomous_business/docs/00_START_HERE.md
3. ~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md
4. ~/Docs/Autonomous_business/docs/contracts/MVOS_10_OUT_OF_10_DECISION_GRADE_ACCEPTANCE_CONTRACT.md
5. ~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
6. ~/Docs/Oracle/Autonomous_business/2026-05-18/154628_TASK-000_mvos-10-out-of-10-acceptance-contract-codecaptain-review/Answer/Code Captain_18.05.2026_16_16_34.md
7. ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos-10-out-of-10-contract-execution/PLAN.md
8. ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_10_OUT_OF_10_CONTRACT_EXECUTION_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md

OPERATING BOUNDARY

You may autonomously run helper agents for:

- read-only analysis;
- copied-temp proofs;
- local tests;
- contract docs;
- source-contract registry updates;
- non-production code changes;
- evidence packaging;
- validate-only owner/operator surfaces;
- internal runbooks;
- retained blocker boards.

You may not, without separate explicit owner authorization and CodeCaptain review:

- mutate production db/app.db;
- mutate excel_ui/SALES_KSP_CRM_V3.xlsx;
- mutate schedulers, LaunchAgents, plist, cron, or automation state;
- write to Web_automation;
- run browser-login automation;
- export credentials, sessions, cookies, storage state, .env, browser profiles, or secrets;
- write to Kaspi/API/WebUI/Google/Meta/ads/banks/external systems;
- publish or send owner-facing outputs;
- move cash;
- approve supplier payment;
- approve PO commitment;
- approve ad spend;
- change prices;
- change stock;
- run production apply.

GLOBAL STOPLINES

Stop immediately and produce a RED closeout if:

- production DB is modified without explicit apply authorization;
- protected workbook is modified without explicit workbook authorization;
- any help/inspection command writes data;
- any write path lacks dry-run default, env gate, or --apply gate;
- copied-temp proof is described as production truth;
- scoped proof is described as full-scope proof;
- retained blockers are hidden;
- missing ads spend is treated as zero without source evidence;
- API lifecycle evidence is used as WebUI status_change_at without accepted contract;
- source contracts conflict;
- owner publication is implied before publication gate;
- cash, PO, ad, price, stock, scheduler, workbook, production DB, or external action is implied without explicit authority.

PHASE 0 - READCHECK AND SCOPE DECLARATION

Create:

- exports/validation/mvos_10_10_goal/<timestamp>/READCHECK.md
- exports/validation/mvos_10_10_goal/<timestamp>/MVOS_SCOPE_PROFILE_DECLARATION.json

Declare exactly one:

- MVOS_SCOPE_FULL_FIVE_STORE
- MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE

If using scoped three-store mode, every artifact must say:

SCOPED_STATUS_LEDGER_STOREB_ACMEWEAR_UNIVERSAL_ONLY
11KZ_AND_MELVIS_EXCLUDED_FROM_CURRENT_OPERATING_SCOPE
NO_FULL_FIVE_STORE_STATUS_LEDGER_GREEN

Gate: GREEN only if scope is explicit and accepted.

PHASE 1 - SOURCE CONTRACT REGISTRY

Create or update:

- docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json

Include every active contract for:

- ads DirectAPI and Meta scope;
- payment evidence root;
- bank/manual cash;
- lifecycle cancellation;
- status ledger scope/provenance;
- COGS route;
- PO/day-complete blockers;
- WebUI status source;
- order-entry source;
- retained blocker handling.

Run:

python3 -m json.tool docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json
python3 scripts/validate_mvos_source_contract_registry.py --strict

If validator does not exist, create tests-first implementation for it.

Gate: GREEN only if no duplicate active domain/scope contracts exist and every materializer source route has a contract.

PHASE 2 - WRITE SAFETY AND BOUNDARY

Sample current protected surfaces:

- db/app.db SHA;
- workbook SHA;
- DB integrity;
- holders/lsof;
- SQLite sidecars;
- protected git status.

Run or implement:

scripts/check_no_db_tracked.sh
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml --strict
python3 scripts/validate_no_help_command_writes.py --strict
pytest -q tests/test_generate_po_dashboard_data_help_no_write.py

Gate: GREEN only if help/inspection commands cannot write and all write-capable commands are gated.

PHASE 3 - SOURCE FRESHNESS AND C3 POLICY GATES

Build a copied-temp DB from current production DB.

Materialize accepted source freshness contracts into the copied DB only.

Run:

python3 scripts/validate_policy_source_freshness.py --db <copied-db> --as-of <as-of> --strict --json
python3 scripts/validate_policy_gate_results.py --db <copied-db> --strict --json

Output:

- SOURCE_FRESHNESS_ACCEPTED_PACKETS_MATRIX.tsv
- SOURCE_FRESHNESS_BLOCKER_MATRIX.tsv
- POLICY_GATE_MATRIX.tsv

Gate: GREEN only if required sources are fresh for declared scope or retained blockers explicitly block publication.

PHASE 4 - DOMAIN GATES IN PARALLEL

Run read-only or copied-temp helper agents in parallel:

Agent A: Orders/Sales/Lifecycle
- Validate order entries, day-complete, status ledger, sales truth, and COGS completeness.
- Preserve cancellation and lifecycle contracts.

Agent B: Ads Truth
- Validate ads source packets, STOREB identity, Meta scope, offer universe, and spend reality.
- Missing spend must be a gap, not zero.

Agent C: Cashflow/Bank
- Validate cashflow invariants, actual/model separation, order cashflow coverage, bank/manual/payment freshness.

Agent D: PO/Stock/Inbound
- Validate stock freshness, PO dashboard invariants, PO/inbound facts, stock ledger/snapshot.

Agent E: Exception Queue
- Validate exception queue schema, retained blockers, owner action list.

All agents must write evidence under the same timestamped MVOS goal root or assigned handoff folder and must not mutate production.

PHASE 5 - OWNER DECISION SURFACES

Build validate-only surfaces:

- Cash Risk Daily
- Daily Survival Brief
- Stock/Order Risk
- Ads/Profit Readiness
- PO/Inbound Readiness

Each must include:

- scope profile;
- DB SHA;
- workbook SHA;
- source dates;
- warning board;
- allowed decisions;
- blocked decisions;
- evidence paths.

Run or implement:

python3 scripts/validate_owner_decision_surface.py --surface cash_risk_daily --strict
python3 scripts/validate_owner_decision_surface.py --surface daily_survival_brief --strict
python3 scripts/validate_owner_decision_surface.py --surface stock_order_risk --strict
python3 scripts/validate_owner_decision_surface.py --surface ads_profit_readiness --strict
python3 scripts/validate_owner_decision_surface.py --surface po_inbound_readiness --strict

Gate: GREEN only if no surface implies unauthorized business action.

PHASE 6 - FULL COPIED-TEMP MVOS PROOF

From current production DB SHA, create copied DB.

Apply only accepted copied-temp materializers and contracts.

Run full validator matrix:

- source freshness;
- policy gates;
- day-complete;
- status ledger;
- PO dashboard;
- ads sidecar/readiness;
- ads offer universe;
- ads spend reality;
- exception queue;
- cashflow;
- COGS;
- owner decision surfaces.

Create:

- FULL_MVOS_COPIED_TEMP_PROOF_BOARD.json
- FULL_MVOS_COPIED_TEMP_PROOF_BOARD.md
- VALIDATOR_EXIT_MATRIX.tsv
- RETAINED_BLOCKER_BOARD.md
- COPIED_DB_BOUNDARY_SHA256.tsv

Gate:

- COPIED_TEMP_GREEN_PROOF only if all required validators pass for declared scope and no unaccepted blockers affect claimed output.
- Otherwise YELLOW_RETAINED_BLOCKER_BOARD_PROOF.

PHASE 7 - PRODUCTION PREFLIGHT PACKET

Only if copied-temp proof is GREEN or a narrow production candidate is explicitly separated.

Prepare:

- PRODUCTION_PREFLIGHT_PACKET.md
- OWNER_APPROVAL_PHRASE_REQUEST.md
- PRODUCTION_BACKUP_AND_ROLLBACK.md
- DRY_RUN_EXPECTED_DIFF.json
- WRITE_COMMAND_MANIFEST.tsv

Do not apply.

Request CodeCaptain review before any owner phrase request.

PHASE 8 - POST-APPLY RELEASE ANCHOR

Only after separate owner phrase and production apply are approved.

Post-apply must produce:

- POST_APPLY_VALIDATION_MATRIX.tsv
- PRODUCTION_DIFF_ACTUAL_VS_EXPECTED.json
- RELEASE_ANCHOR.md
- RELEASE_ANCHOR.json
- ROLLBACK_POINTER.md

PHASE 9 - REPEATED RUN AND AUTONOMY

Only after production is anchored.

Run at least 3 consecutive validate-only daily cycles.

Create:

- MVOS_REPEATED_RUN_MATRIX.tsv
- AUTOMATION_PAUSE_RESUME_EVIDENCE.md
- SCHEDULER_HEARTBEAT_REPORT.json
- DAILY_AUTONOMY_RUNBOOK_CURRENT.md

Gate: GREEN only if the system runs repeatedly without rediscovery, keeps warnings visible, and fails closed.

PHASE 10 - OWNER PUBLICATION AND LIVE AUTHORITY

Only after all prior gates.

Create:

- OWNER_PUBLICATION_GREEN_PACKET.md
- OWNER_VISIBLE_WARNING_BOARD.md
- OWNER_DECISIONS_ALLOWED_BLOCKED_MATRIX.tsv
- MVOS_10_OUT_OF_10_ACCEPTANCE_PACKET.md
- MVOS_10_OUT_OF_10_ACCEPTANCE_PACKET.json

Request CodeCaptain review and owner approval.

SUCCESS CRITERIA

The goal succeeds only if:

1. MVOS scope is explicit.
2. Source contract registry is valid.
3. Boundary/write safety passes.
4. Source freshness and policy gates pass or retained blockers visibly block publication.
5. Domain gates pass for declared scope.
6. Owner decision surfaces pass.
7. Full copied-temp proof is GREEN for declared scope.
8. Production preflight/apply is reviewed and owner-authorized if required.
9. Post-apply release anchor is green.
10. At least 3 repeated daily validate-only runs pass.
11. Owner publication packet is green.
12. Final acceptance packet exists.

If any gate remains YELLOW, produce the next smallest safe action.

If any gate is RED, stop and report the exact cause.
```
