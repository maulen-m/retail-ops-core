# Agent 1 Starter - Final Creative Meta Publish

You are Agent 1. You are the serialized final LINE31 creative publish-readiness agent.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_final_creative_meta_publish/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md`
6. `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/closeout.md`
7. `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_publish_intake_and_approval.md`
8. `~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json`
9. `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
10. The latest `latest_drop_intake.checklist_path` from `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
11. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
12. `~/Docs/Business_3/Facebook_ads/docs/10_CONTRACTS/META_API_PRIMARY_AND_WRITE_GATE_CONTRACT.md`

## Task

Prepare or execute the final LINE31 countrywide Meta launch step, depending on whether final creative mapping and exact owner approval are present.

Required:

- capture protected DB/workbook hashes before work;
- refresh the current non-creative matrix with `scripts/build_line31_current_noncreative_gate_matrix.py`;
- run `scripts/validate_line31_owner_objective_source_freshness.py --json` so cash/SHR/LINE31 stock owner facts are source-backed before launch decisions;
- build the read-only LINE31 launch preflight packet;
- refresh the stable `docs/current/LINE31_LAUNCH_CURRENT_STATUS.*` operator pointer with `scripts/write_line31_current_launch_status.py --json`;
- read `docs/current/LINE31_LAUNCH_CURRENT_STATUS.json` after refresh and use its `latest_drop_intake.checklist_path` as the current final creative intake checklist; do not hard-code an older timestamped drop folder;
- read `FINAL_CREATIVE_DROP_CHECKLIST.json` before touching final assets; follow its exact-one video/thumbnail requirements, required mapping fields, placeholder replacement list, tracking/redirect QA evidence requirement, approval policy, safety boundaries, and internal Kaspi keep-on policy;
- run `scripts/validate_line31_current_final_creative_drop.py --json` after refreshing the stable pointer so the agent validates the current latest drop folder instead of a stale timestamped folder;
- run the active-goal completion audit and do not call the goal complete unless it passes; the audit refreshes the current non-creative matrix by default and must still fail until final creative/approval evidence is strict-valid;
- treat `exports/validation/line31_current_noncreative_gate_refresh_current/CURRENT_NONCREATIVE_GATE_MATRIX.json` as the current non-creative decision surface after refresh; do not stop solely because the older Round 3 historical matrix is stale or `YELLOW`;
- if a final creative drop folder is provided, first run `scripts/validate_line31_final_creative_drop_intake.py` with the intended final asset URI and Kaspi CTA URL; stop `YELLOW` if it reports ambiguous media, placeholder URLs, or invalid approval text;
- if a final creative drop folder is provided, prefer `scripts/prepare_line31_launch_readiness_from_assets.py --asset-dir ...` to auto-detect exactly one video and one thumbnail, require `--tracking-qa-evidence-file` when owner approval is present, record approval evidence when present, generate the mapping, and rebuild the preflight packet in one local-only run;
- if the drop folder contains multiple candidate videos or thumbnails, stop `YELLOW` or pass explicit `--video` and `--thumbnail` paths after confirming the intended files;
- use `scripts/prepare_line31_final_creative_mapping.py` only for narrower mapping-only repair work instead of manually editing hash fields;
- verify the final creative mapping JSON;
- if final local files exist, compute SHA-256 and compare to mapping;
- run strict creative validator;
- record advisory broader repo-health checks separately with `validate_params.py --strict` and EOD dry-run with `--skip-api-sync`;
- do not treat `repo_wide_advisory` failures as LINE31 launch blockers unless the current matrix also exposes a failing row with `scope=line31_launch_blocking`;
- confirm whether the exact owner approval phrase from the intake file has been provided in a separate approval-evidence file;
- confirm whether current tracking/redirect QA JSON evidence is present, `gate=GREEN`, and referenced in the mapping by `tracking_redirect_qa.evidence_path` plus matching `tracking_redirect_qa.evidence_sha256`;
- if the owner phrase has been provided as a text file or stdin and you are not using the one-shot helper, use `scripts/record_line31_owner_publish_approval.py --require-mapping-ready` to record canonical local evidence and SHA only after the final creative mapping is populated and valid except for the expected pending owner-approval boolean;
- if approval is missing, stop at readiness with no publish;
- use `~/Docs/Business_3/Facebook_ads` as the primary Meta execution/control repo; run its API-primary read-only preflight before any Meta publish conversation;
- treat Chrome/Ads Manager UI as fallback only when the Graph API preflight is blocked or cannot expose the required evidence;
- do not treat `ENABLE_META_WRITE=1` as approval; it is capability only and must still be paired with the exact action-specific owner phrase generated from a preflight evidence lock;
- if approval is present and every gate passes, proceed only with the exact LINE31 countrywide Meta publish scope;
- capture protected DB/workbook hashes after work;
- write closeout.

## Required Commands

Run at minimum:

```bash
python3 scripts/build_line31_current_noncreative_gate_matrix.py --json
python3 scripts/validate_line31_owner_objective_source_freshness.py --json
python3 scripts/build_line31_launch_preflight_packet.py --json
python3 scripts/audit_line31_active_goal_completion.py --json
python3 scripts/report_line31_next_launch_action.py
python3 scripts/write_line31_current_launch_status.py --json
python3 -m json.tool docs/current/LINE31_LAUNCH_CURRENT_STATUS.json
python3 scripts/validate_line31_current_final_creative_drop.py --json
python3 scripts/record_line31_owner_publish_approval.py --help
python3 scripts/validate_line31_final_creative_drop_intake.py --help
python3 scripts/prepare_line31_final_creative_mapping.py --help
python3 scripts/prepare_line31_launch_readiness_from_assets.py --help
python3 -m json.tool exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json
python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative
python3 scripts/validate_line31_final_creative_mapping.py
python3 scripts/validate_line31_launch_readiness.py
bash scripts/lint_docs.sh
git diff --check
```

Meta API primary preflight, run from `~/Docs/Business_3/Facebook_ads`:

```bash
PYTHONPATH=. python3 scripts/preflight_meta_api_primary.py --live-readonly --json
```

Advisory broader repo-health commands to run and log separately:

```bash
python3 scripts/validate_params.py --strict
python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose
```

Standalone owner approval recorder template, only after final creative mapping is filled:

```bash
python3 scripts/record_line31_owner_publish_approval.py \
  --require-mapping-ready \
  --mapping exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/final_creative_asset_mapping_template.json \
  --approval-text-file /absolute/path/to/pasted_owner_approval.txt \
  --json
```

Before final creative is ready, `python3 scripts/validate_line31_launch_readiness.py --allow-pending-creative` may pass as `GREEN_EXCEPT_CREATIVE` only if the latest non-creative synthesis matrix is also green. `build_line31_launch_preflight_packet.py`, `prepare_line31_launch_readiness_from_assets.py`, and `audit_line31_active_goal_completion.py` refresh or pass through the current matrix by default. If readiness fails as `YELLOW` because of retained non-creative blockers, do not publish and route to strict blocker repair or exact owner acceptance first. Strict `python3 scripts/validate_line31_final_creative_mapping.py` and strict `python3 scripts/validate_line31_launch_readiness.py` are expected to fail until final creative, current tracking/redirect QA evidence, and approval evidence exist.

## Required Outputs

Evidence folder:

`~/Docs/Autonomous_business/exports/validation/line31_final_creative_meta_publish_20260601/`

Required files:

- `FINAL_CREATIVE_MAPPING_VALIDATION.md`
- `FINAL_CREATIVE_MAPPING_VALIDATION.json`
- `LINE31_LAUNCH_PREFLIGHT_PACKET_PATH.txt`
- `COMMANDS_RUN.tsv`
- `PROTECTED_SURFACE_HASHES.tsv`
- `EXTERNAL_ACTION_LOG.md`
- `RETAINED_BLOCKERS.md`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_final_creative_meta_publish/agent1_final_creative_meta_publish_closeout.md`

Closeout gate must be exactly one of:

- `Gate: GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH`
- `Gate: GREEN_PUBLISHED`
- `Gate: YELLOW`
- `Gate: RED`

## Approval Boundary

Do not publish unless:

- the mapping validator passes in strict mode;
- final creative URI/thumbnail/SHA evidence is present;
- current tracking/redirect QA evidence is present and SHA-verified;
- exact owner approval phrase from the intake file is present after mapping is filled;
- `publish_authority.approval_evidence_path` points to a separate file containing that exact phrase and `approval_evidence_sha256` matches;
- protected surfaces are stable or any authorized write is backup-first and logged.

Do not pause internal Kaspi LINE31 campaigns unless there is a separate explicit owner approval phrase for that action.

## Stop Conditions

Stop `YELLOW` if final creative mapping or owner approval is missing.

Stop `YELLOW` if the latest non-creative matrix still blocks `GREEN_EXCEPT_CREATIVE`.

Stop `RED` if:

- protected DB/workbook drift appears without authorization;
- external tooling attempts unrelated writes;
- requested publish scope expands beyond LINE31 countrywide Meta;
- any lane tries to pause internal Kaspi LINE31 campaigns without separate approval.
