# H5 Operational Proving Run Contract

## Purpose
Define the production proving window contract for final autonomy closure:
- 14 consecutive daily cycles,
- all hard gates green,
- fail-closed exception handling.

## Run Window
- Duration: 14 consecutive days.
- Day key: `<YYYY-MM-DD>` in Asia/Qyzylorda timezone.
- Every day must produce a complete artifact set.

## Required Daily Artifacts
- `exports/daily/<day>/daily_ops_report.json`
- `exports/daily/<day>/scheduler_heartbeat.json`
- `exports/daily/<day>/sales_vs_waybill_parity.json`
- `exports/validation/business_insides_economics/<day>/economics_ready_report.json`
- `exports/validation/ads_sidecar_readiness/<day>/ads_sidecar_readiness_report.json`
- `exports/validation/business_insides_ocean_drop_alignment/<day>/alignment_report.json`
- `exports/validation/ops_selection_parity/<day>/parity_report.json`
- `exports/validation/archive_pack_integrity/ui/<day>/integrity_report.json`
- `exports/owner_pnl/<day>/OWNER_PNL.json`
- `exports/daily/<day>/sales_truth_external_reference_parity.json` *(required when `AB_KASPI_ETL_ARCHIVE_DIR` or `AB_KASPI_ETL_REFERENCE_DIR` is configured)*
- `exports/exceptions/<day>/exceptions.json`
- `exports/diagnostics/<day>/system_health.json`
- `exports/perf/<day>/daily_ops_timings.json`
- `exports/daily/<day>/truth_drift_report.json`

## Weekly Artifacts
- `exports/health/weekly/<YYYY-W##>/weekly_health_scorecard.json`

## Hard Gates (daily)
- `python3 scripts/run_h5_proving_day.py --strict --project-root <REPO_PATH> --as-of <day>`
- Equivalent expanded chain (for debugging):
  - `python3 scripts/system_doctor.py --strict --project-root <REPO_PATH> --as-of <day>`
  - `python3 scripts/validate_as_of_consistency.py --strict --project-root <REPO_PATH> --as-of <day>`
  - `python3 scripts/validate_business_insides_economics_ready.py --as-of <day> --strict`
  - `python3 scripts/validate_ads_sidecar_readiness.py --as-of <day> --strict`
  - `python3 scripts/validate_business_insides_ocean_drop_alignment.py --as-of <day> --strict`
  - `python3 scripts/build_owner_pnl_report.py --as-of <day> --strict`
  - `python3 scripts/validate_ops_selection_parity.py --as-of <day> --strict`
  - `python3 scripts/validate_scheduler_heartbeat.py --as-of <day> --strict`
  - `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --as-of <day> --strict`
  - `python3 scripts/validate_sales_truth_external_reference.py --strict-if-configured --project-root <REPO_PATH> --as-of <day>`
  - `python3 scripts/triage_exceptions.py --strict --exceptions exports/exceptions/<day>/exceptions.json`
  - `python3 scripts/validate_h5_artifact_set.py --strict --project-root <REPO_PATH> --as-of <day>`

## Day-0 Kickoff Commands (copy/paste)
```bash
cd <REPO_PATH>
DAY="<YYYY-MM-DD>"

python3 scripts/system_doctor.py --strict --project-root . --as-of "$DAY"
python3 scripts/validate_as_of_consistency.py --strict --project-root . --as-of "$DAY"
python3 scripts/validate_business_insides_economics_ready.py --as-of "$DAY" --strict
python3 scripts/validate_ads_sidecar_readiness.py --as-of "$DAY" --strict
python3 scripts/validate_business_insides_ocean_drop_alignment.py --as-of "$DAY" --strict
python3 scripts/build_owner_pnl_report.py --as-of "$DAY" --strict
python3 scripts/validate_ops_selection_parity.py --as-of "$DAY" --strict
python3 scripts/validate_scheduler_heartbeat.py --as-of "$DAY" --strict
python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --as-of "$DAY" --strict
python3 scripts/triage_exceptions.py \
  --exceptions "exports/exceptions/$DAY/exceptions.json" \
  --playbook docs/ops/EXCEPTION_PLAYBOOK.md \
  --allowlist config/exceptions_allowlist.json \
  --strict
python3 scripts/validate_h5_artifact_set.py --strict --project-root . --as-of "$DAY"

# One-command deterministic proving run (preferred)
python3 scripts/run_h5_proving_day.py --strict --project-root . --as-of "$DAY"
```

## Stop-the-Line
- Any hard gate failure.
- Missing artifact for a day.
- Critical exception not fixed or explicitly allowlisted.
- Any uncontrolled write path activation.

## Completion
Run is complete only when:
- all 14 days are green,
- no artifact gaps,
- final board evidence references all day folders and weekly summaries.
