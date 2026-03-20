# RELEASE_POLICY_OPERATE_MODE

## Purpose
Enforce ROI-first delivery after sales-truth stabilization.  
No new work ships unless it improves profit, capital safety, or operator time.

## Required Release Bundle
Every change set must include all of the following:
- `roi_claim`: measurable target (`profit_kzt`, `capital_at_risk_kzt`, `ops_minutes_saved`, or `risk_reduction`).
- `gate_transcript_path`: exact path to a green transcript under `exports/validation/...`.
- `rollback_plan`: git rollback steps and DB restore steps (if any apply/write path was executed).
- `failure_mode`: what turns the release RED (explicit stop-the-line condition).

## Fail-Closed Policy
- Missing required bundle fields -> release is invalid.
- Any skipped gate -> release is invalid.
- Any write path without `--apply` + env gate + DB backup + apply manifest -> release is invalid.

## Mandatory Baseline Gates
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/validate_single_truth_system.py`
- `bash scripts/lint_docs.sh`

## ROI Gate
Changes must map to at least one:
- Profit accuracy/trust (economics publication integrity)
- Capital protection (PO risk gates, caps, rollback safety)
- Daily ops reliability/time reduction (autopilot, scheduler health, exception clarity)

Changes that do not map to ROI gate are deferred.

## Rollback Standard
- Code rollback: `git revert <sha>` (no force reset).
- DB rollback: restore the exact pre-apply backup path recorded in evidence.
- Re-run strict gates after rollback to verify known-good state.
