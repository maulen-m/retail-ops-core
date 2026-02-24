# Kaspi Daily Ops Orchestrator Runbook

## Purpose
Run a deterministic, fail-closed daily ops chain with one command.

Primary entrypoint:
- `python3 scripts/run_kaspi_daily_ops.py --as-of <YYYY-MM-DD>`

Supported profiles:
- `--profile today-fast`: strict current-day waybill checks (`--since-days 1`, no overdue expansion)
- `--profile catch-up`: overdue-inclusive window (`--since-days 3 --include-overdue`)

## What It Runs
1. `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`
2. `python3 scripts/check_anchor_health.py --project-root <REPO_PATH> --as-of <date>`
3. `python3 scripts/ops_status.py --project-root <REPO_PATH>`
4. `python3 scripts/preflight_shipment.py --project-root <REPO_PATH>`
5. `python3 scripts/report_waybill_status.py --strict-stopline` for each active store in `config/stores.yaml`
6. `python3 scripts/build_ops_drift_pack.py --as-of <date>`
7. `python3 scripts/validate_drift_pack_slo.py --strict --as-of <date>`

Store roster source:
- default: `config/stores.yaml`
- override: `--stores-config <path>`

## Output Artifacts
Default output root:
- `exports/validation/board_v6_runtime/<YYYY-MM-DD>/`

Files:
- `daily_ops_summary.json`
- `daily_ops_summary.md`

Summary artifact fields include:
- `profile`
- `stores_config`
- `steps[].duration_sec`
- `total_duration_sec`

## Benchmark + Timing Validation
Generate benchmark timing artifacts:

```bash
python3 scripts/benchmark_kaspi_daily_ops.py \
  --as-of <YYYY-MM-DD> \
  --profile today-fast \
  --output-dir exports/validation/board_v7_<YYYY-MMDD>/V7-C1_PARITY
```

Validate artifact structure (fail-closed in strict mode):

```bash
python3 scripts/validate_daily_ops_timing_artifact.py \
  exports/validation/board_v7_<YYYY-MMDD>/V7-C1_PARITY/benchmark_timings.json \
  --strict
```

Timing policy authority:
- `docs/ops/DAILY_OPS_TIMING_SLO_POLICY.md`

## Failure Behavior
- Any failed step exits non-zero.
- Store-level waybill failure stops the run unless explicitly overridden with:
  - `--allow-store-failure <STORE_CODE>` (repeatable)

## Safety Contract
- Dry-run default.
- `--apply` is currently blocked by design and requires both:
  - `ENABLE_DAILY_OPS_APPLY=1`
  - explicit `--apply`
