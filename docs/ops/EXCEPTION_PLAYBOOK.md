# Exception Playbook

## Purpose
Map each autopilot exception code to an owner and a deterministic remediation step.

Use this with:
- `docs/ops/EXCEPTIONS_SCHEMA_CONTRACT.md`
- `scripts/triage_exceptions.py`

## Exception Code Mapping

| exception_code | severity | owner | recommended_action |
|---|---|---|---|
| `run_kaspi_daily_ops` | `critical` | `ops-codex` | Review `daily_ops_summary.md`, fix failed store/runtime checks, rerun strict profile. |
| `generate_daily_ops_report` | `high` | `ops-codex` | Regenerate report from fresh summary artifact, then validate schema. |
| `validate_daily_ops_report` | `critical` | `ops-codex` | Fix schema errors in `daily_ops_report.json`; rerun strict validator. |
| `build_domain_scorecards` | `critical` | `ops-codex` | Resolve domain red signals (`po`, `inventory`, `cashflow`, `truth_drift`) and rebuild scorecards. |
| `validate_cashfloor` | `critical` | `ops-codex` | Resolve cashfloor breach and rerun validator; block publication until PASS. |
| `translate_transfer_ledger_to_cashflow` | `high` | `ops-codex` | Repair translation contract failures and rerun strict translation validation. |
| `build_daily_ops_timings` | `high` | `ops-codex` | Fix timing/parity regression root cause, regenerate timing artifact. |
| `build_weekly_health_scorecard` | `medium` | `ops-codex` | Restore missing daily diagnostics and rebuild weekly scorecard. |
| `build_green_streak_tracker` | `high` | `ops-codex` | Restore missing gate transcripts/daily reports; rerun streak tracker. |
| `system_doctor` | `critical` | `ops-codex` | Resolve blocked doctor layer and rerun `system_doctor --strict`. |

## Explicit Critical Allowlist Contract

Temporary allowlist entries are stored at:
- `config/exceptions_allowlist.json`

Rules:
- every allowlisted code must exist in the table above;
- each allowlist row must include `reason` and `expires_on`;
- allowlist is temporary and expires automatically.

Strict triage command:

```bash
python3 scripts/triage_exceptions.py \
  --exceptions exports/exceptions/<YYYY-MM-DD>/exceptions.json \
  --playbook docs/ops/EXCEPTION_PLAYBOOK.md \
  --allowlist config/exceptions_allowlist.json \
  --strict
```
