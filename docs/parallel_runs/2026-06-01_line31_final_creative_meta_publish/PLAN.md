# LINE31 Final Creative Meta Publish Plan

Created: 2026-06-01 15:28 +05

Gate target: `GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH`

## Objective

When final LINE31 creative videos are ready, convert the current green dry-run launch state into a strict publish-ready packet and, only with exact owner approval, hand off or execute the LINE31 countrywide Meta publish step.

This plan exists so the launch moment does not rely on memory, chat scrolling, or manual checklist reconstruction.

## Current Authority

Current Autonomous_business readiness evidence:

- `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/closeout.md`
- gate: `GREEN_DRY_RUN_EOD_SUCCESS_WITH_DECLARED_WARNINGS`
- current correction: the current non-creative matrix refresh is `GREEN` for LINE31 launch-blocking gates, so final creative mapping, current tracking/redirect QA evidence, and exact owner approval are the active launch blockers
- broad repo health: `validate_params.py --strict` may be recorded as `YELLOW_ADVISORY`; this is visible in `advisory_repo_blockers` but is not LINE31 launch-blocking unless a current matrix row with `scope=line31_launch_blocking` fails
- retained blockers for LINE31 launch scope: final creative asset URI/thumbnail/SHA mapping, current tracking/redirect QA evidence, and exact owner Meta publish approval evidence

Current final creative intake:

- `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_publish_intake_and_approval.md`
- `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json`
- stable pointer: `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
- current final creative drop checklist: read `latest_drop_intake.checklist_path` from that stable pointer; do not hard-code an older timestamped drop-intake folder.

Readiness contract:

- `~/Docs/Autonomous_business/docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md`

Meta execution/control repo:

- `~/Docs/Business_3/Facebook_ads`
- API-primary contract: `~/Docs/Business_3/Facebook_ads/docs/10_CONTRACTS/META_API_PRIMARY_AND_WRITE_GATE_CONTRACT.md`
- read-only preflight command: `PYTHONPATH=. python3 scripts/preflight_meta_api_primary.py --live-readonly --json`
- `ENABLE_META_WRITE=1` is capability only; it does not authorize campaign/ad/ad set/creative/audience/budget/status/URL mutation without the exact action-specific owner phrase generated from the preflight evidence lock.

Current non-creative synthesis matrix:

- `~/Docs/Autonomous_business/exports/validation/line31_current_noncreative_gate_refresh_current/CURRENT_NONCREATIVE_GATE_MATRIX.json`
- refresh command: `python3 scripts/build_line31_current_noncreative_gate_matrix.py --json`
- fallback historical matrix: `~/Docs/Autonomous_business/exports/validation/line31_green_except_creative_round3_strict_unrelated_repair_20260601/final_synthesis/FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.json`
- launch preflight, one-shot final-assets readiness, and active-goal completion audit all refresh or pass through the current non-creative matrix by default.

Validator:

- `python3 scripts/build_line31_launch_preflight_packet.py --json`
- `python3 scripts/audit_line31_active_goal_completion.py --json`
- `python3 scripts/validate_line31_owner_objective_source_freshness.py --json`
- `python3 scripts/record_line31_owner_publish_approval.py --help`
- `python3 scripts/validate_line31_final_creative_drop_intake.py --help`
- `python3 scripts/validate_line31_current_final_creative_drop.py --json`
- `python3 scripts/prepare_line31_final_creative_mapping.py --help`
- `python3 scripts/prepare_line31_launch_readiness_from_assets.py --help`
- `python3 scripts/report_line31_next_launch_action.py`
- `python3 scripts/write_line31_current_launch_status.py --json`
- `python3 scripts/validate_line31_final_creative_mapping.py --template-ok`
- `python3 scripts/validate_line31_final_creative_mapping.py`
- `python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative`
- `python3 scripts/validate_line31_launch_readiness.py`

## Required Sequence

1. Refresh current repo evidence:
   - read local `AGENTS.md`;
   - read this plan;
   - read the LINE31 final creative launch readiness contract;
   - read the LINE31 closeout and final creative intake files;
   - run `python3 scripts/build_line31_current_noncreative_gate_matrix.py --json` so the current validators supersede stale historical synthesis evidence;
   - run `python3 scripts/validate_line31_owner_objective_source_freshness.py --json` so cash/SHR/LINE31 stock objective facts are backed by the current workbook/source packet before launch decisions;
   - run `python3 scripts/build_line31_launch_preflight_packet.py --json` to create the current read-only launch evidence snapshot;
   - run `python3 scripts/report_line31_next_launch_action.py` to summarize current status;
   - run `python3 scripts/write_line31_current_launch_status.py --json` to refresh the stable `docs/current` operator pointer to the latest preflight/drop-intake evidence;
   - run the Facebook_ads Meta API primary read-only preflight from `~/Docs/Business_3/Facebook_ads`;
   - parse `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` and read its `latest_drop_intake.checklist_path` before processing final creative files;
   - follow the latest `FINAL_CREATIVE_DROP_CHECKLIST.json` exact-one video/thumbnail requirements, required mapping fields, placeholder replacement list, tracking/redirect QA evidence requirement, approval policy, safety boundaries, and internal Kaspi keep-on policy;
   - run `python3 scripts/validate_line31_current_final_creative_drop.py --json` to validate the latest drop folder selected by the stable pointer before any mapping or owner-approval evidence write;
   - if status is `YELLOW` because of LINE31 launch-blocking current non-creative matrix rows, stop before publish and route to the strict non-creative repair/owner-acceptance lane;
   - confirm current protected DB/workbook hashes before doing any launch work.
2. Populate or verify final creative mapping:
   - if using a final creative drop folder, run `scripts/validate_line31_final_creative_drop_intake.py` first to reject ambiguous media, placeholder URLs, and optional approval-text mistakes before writing mapping evidence;
   - prefer `scripts/prepare_line31_launch_readiness_from_assets.py` when final local video and thumbnail files are available because it requires tracking/redirect QA evidence when owner approval is present, records approval evidence when provided, writes the mapping, and rebuilds the preflight packet in one local-only run;
   - use `scripts/prepare_line31_final_creative_mapping.py` only when a narrower mapping-only step is needed;
   - one row per final creative;
   - include local path or final remote URI;
   - include thumbnail path/URI;
   - include video SHA-256 and thumbnail SHA-256 when local;
   - include `tracking_redirect_qa.evidence_path` and matching `tracking_redirect_qa.evidence_sha256` for current LINE31 tracking/redirect QA JSON;
   - include `utm_content` and `utm_placement`;
   - include final landing URL preserving `utm_source=meta`, `utm_medium=paid_social`, `utm_campaign=line31_countrywide`, `utm_content`, and `utm_placement`.
3. Run strict LINE31 launch validators:
   - `python3 -m json.tool exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json`;
   - `python3 scripts/validate_line31_owner_objective_source_freshness.py --json`;
   - `python3 scripts/build_line31_launch_preflight_packet.py --json`;
   - `python3 scripts/audit_line31_active_goal_completion.py --json`;
   - `python3 scripts/record_line31_owner_publish_approval.py --help`;
   - `python3 scripts/validate_line31_final_creative_drop_intake.py --help`;
   - `python3 scripts/validate_line31_current_final_creative_drop.py --json`;
   - `python3 scripts/prepare_line31_final_creative_mapping.py --help`;
   - `python3 scripts/prepare_line31_launch_readiness_from_assets.py --help`;
   - `python3 -m json.tool docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`;
   - `python3 scripts/validate_line31_final_creative_mapping.py`;
   - `python3 scripts/validate_line31_launch_readiness.py`.
4. Record advisory broader repo-health checks separately:
   - `python3 scripts/validate_params.py --strict`;
   - `python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose`;
   - if these fail only through `repo_wide_advisory` current-day operational or derived-report facts, log them as advisory and do not publish-label them as LINE31 launch blockers.
5. Confirm exact owner approval phrase is present in a separate approval-evidence file.
6. If using the standalone approval recorder, require `--require-mapping-ready` so the owner phrase cannot be recorded against an empty or placeholder creative mapping. The one-shot helper may record approval while generating the mapping because it validates the produced mapping immediately.
   - standalone recorder template: `python3 scripts/record_line31_owner_publish_approval.py --require-mapping-ready --mapping exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json --approval-text-file /absolute/path/to/pasted_owner_approval.txt --json`
7. If approval is missing, stop at `YELLOW_READY_FOR_OWNER_PUBLISH_APPROVAL`.
8. Before calling the active goal complete, require `python3 scripts/audit_line31_active_goal_completion.py --json` to pass; this audit refreshes the current non-creative matrix by default and must still fail if final creative, tracking/redirect QA, or approval evidence is missing.
9. If approval is present and validators pass, proceed only within the LINE31 countrywide Meta publish scope.
   - use Meta Graph API as the primary route;
   - use Chrome/Ads Manager UI only as fallback if API evidence or execution is blocked;
   - every Meta mutation must use an exact owner approval phrase tied to the current preflight evidence lock.
10. Write launch evidence and closeout.

## Required Owner Approval Phrase

The required phrase is maintained in:

`~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_publish_intake_and_approval.md`

The phrase must be pasted after final creative mapping and current tracking/redirect QA evidence are filled and verified. Do not infer approval from prior broad approvals, and do not accept `publish_authority.approved=true` unless `approval_evidence_path` points to a separate file containing the exact phrase and `approval_evidence_sha256` matches that file.

## Guardrails

Allowed before final approval:

- read-only/local evidence refresh;
- filling or validating local mapping files;
- hash calculation;
- local dry-runs;
- handoff/closeout writing.

Allowed after exact final approval, if validators pass:

- LINE31 countrywide Meta publish action only, according to the approved creative mapping and existing landing-page tracking contract;
- required local launch logging/evidence.

Not allowed without separate approval:

- pausing internal Kaspi LINE31 campaigns;
- unrelated Meta campaign changes;
- bid/budget changes outside the exact approved LINE31 publish scope;
- price changes;
- stock changes;
- Kaspi/WebUI/API writes;
- production workbook writes;
- scheduler/source-pointer changes;
- supplier payment;
- PO commitment;
- cash movement;
- owner publication outside this launch.

## Stop Conditions

Stop as `RED` if protected DB/workbook hashes drift during the lane without authorized write gate.

Stop as `YELLOW` if:

- the current non-creative matrix does not allow `GREEN_EXCEPT_CREATIVE`;
- final creative mapping is incomplete;
- strict creative validator fails;
- owner publish approval phrase is missing;
- EOD dry-run fails for non-creative reasons;
- Chrome/Meta tooling is unavailable but local readiness can still be proven.

Stop as `RED` if:

- any tool attempts unrelated external writes;
- the scope expands beyond LINE31 countrywide Meta launch;
- internal Kaspi LINE31 campaigns are paused without separate approval.

## Closeout Requirements

Write final closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_final_creative_meta_publish/agent1_final_creative_meta_publish_closeout.md`

Closeout must include:

- `Gate: GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH`, `Gate: GREEN_PUBLISHED`, `Gate: YELLOW`, or `Gate: RED`;
- exact creative ids and hashes used;
- exact landing URLs and UTM values;
- exact owner approval phrase if publish occurred;
- command log;
- protected DB/workbook before/after hashes;
- external action log, if any;
- rollback or restore notes where applicable.
