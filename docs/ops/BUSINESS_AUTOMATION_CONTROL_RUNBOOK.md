# Business Automation Control Runbook

Status: canonical operational control surface.
Created: `2026-05-13 18:08 +05`.

## Purpose

This runbook prevents rediscovering the daily automation pause/resume sequence from scratch.
Use it when a frozen proof window, repo repair lane, or live-ops recovery requires turning
business automations off and then restoring them quickly.

The canonical control surfaces are:

- `config/business_automation_manifest.json`
- `scripts/manage_business_automation.py`
- evidence under `exports/automation_control/`

## Safety Contract

- `status` and dry-run `pause` / `resume` are read-only inspection paths.
- Real launchd mutation requires both `--apply` and `ENABLE_BUSINESS_AUTOMATION_CONTROL=1`.
- The command must write evidence for every pause/resume/verify run.
- Do not manually boot out or bootstrap labels one-by-one unless this command is broken and the breakage is recorded.
- Do not claim the repo is frozen unless `verify --expect paused` is green for the intended scope.
- Do not claim daily business automation is restored unless `verify --expect running` is green for the intended scope.

## Scopes

- `daily-ops`: order import/fetch, Google Ops Board publish/writeback/READY watcher, closeout backstop, Telegram control, shipped-truth sync, daily ops report.
- `ab-business`: all known Autonomous_business-local business LaunchAgents.
- `all-business`: Autonomous_business plus known Web_automation business LaunchAgents that can affect frozen-boundary proof work.

Use `daily-ops` for normal daily order-processing recovery. Use wider scopes only when a proof window or repo freeze actually requires them.

## Fast Status Check

```bash
python3 scripts/manage_business_automation.py status \
  --scope daily-ops \
  --output-json exports/automation_control/status_latest.json
```

Expected live day outcome: all selected labels loaded.

## Planned Pause

Dry-run first:

```bash
python3 scripts/manage_business_automation.py pause \
  --scope daily-ops \
  --output-json exports/automation_control/pause_dry_run_latest.json
```

Apply only after the dry-run matches the intended scope:

```bash
ENABLE_BUSINESS_AUTOMATION_CONTROL=1 \
python3 scripts/manage_business_automation.py pause \
  --scope daily-ops \
  --apply \
  --output-json exports/automation_control/pause_apply_latest.json
```

Verify the frozen state:

```bash
python3 scripts/manage_business_automation.py verify \
  --scope daily-ops \
  --expect paused \
  --output-json exports/automation_control/verify_paused_latest.json
```

## Planned Resume

Dry-run first:

```bash
python3 scripts/manage_business_automation.py resume \
  --scope daily-ops \
  --output-json exports/automation_control/resume_dry_run_latest.json
```

Apply only when the listed labels and plist paths are correct:

```bash
ENABLE_BUSINESS_AUTOMATION_CONTROL=1 \
python3 scripts/manage_business_automation.py resume \
  --scope daily-ops \
  --apply \
  --output-json exports/automation_control/resume_apply_latest.json
```

Verify restored business automation:

```bash
python3 scripts/manage_business_automation.py verify \
  --scope daily-ops \
  --expect running \
  --output-json exports/automation_control/verify_running_latest.json
```

Fast daily shipping helper:

```bash
ENABLE_BUSINESS_AUTOMATION_CONTROL=1 \
python3 scripts/run_daily_shipping_enablement.py \
  --target-date today \
  --output-json exports/automation_control/daily_shipping_enable_latest.json \
  enable --apply
```

This helper intentionally limits the enable step to status, dry-run resume,
apply resume, and running verification. It does not run CRM import, Google board
publish, or Telegram delivery validation as part of the resume itself.

After the all-store 17:00 Asia/Almaty shipping cutoff has passed, run the
post-cutoff validation separately:

```bash
python3 scripts/run_daily_shipping_enablement.py \
  --target-date today \
  --output-json exports/automation_control/daily_shipping_validate_latest.json \
  validate
```

Before the cutoff, `validate` exits as `DEFER_UNTIL_POST_CUTOFF` unless
`--wait-until-cutoff` is supplied. This keeps the daily resume path fast while
preserving the DB-first closeout health profile and Google Ops Board
validate-only proof required for shipping. The routine shipping green gate does
not depend on the local CRM workbook.

## Main-Goal Integration

The full business-system goal is not just green reports. The repo must operate as a
repeatable business control system. That means frozen proof windows and live daily operations
must have an explicit off/on workflow with evidence, not improvised launchd commands.

Option C readiness includes this automation-control capability:

- pause safely before boundary-sensitive proof work;
- verify no selected business agents are running while proof work is frozen;
- resume the exact required business automation scope after the proof lane;
- verify daily order processing, Google Ops Board, closeout, Telegram control, and shipped-truth jobs are loaded again.

## Failure Handling

If `verify --expect paused` is red:

- read the generated `verify_report.json`;
- check which labels remain loaded;
- check protected-surface holders and SQLite sidecars;
- do not start boundary-sensitive proof work until the reason is resolved or explicitly accepted.

If `verify --expect running` is red:

- read the generated `verify_report.json`;
- check missing plist paths in the status report;
- rerun `resume --scope <scope>` after repairing the plist or installer path;
- do not assume the daily Google board / Telegram closeout path is live until the running verify is green.
