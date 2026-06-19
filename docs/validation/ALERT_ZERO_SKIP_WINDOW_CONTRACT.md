# G-ALERT-02 Zero-Skip Window Contract

Gate: G-ALERT-02

Purpose: prove that the alert repair has survived the required elapsed window without returning to the historical "Telegram alert skipped" failure mode.

## Proof Surface

The report reads only local scheduler stdout logs:

- `logs/single_truth_preflight_stdout.log`
- `logs/on_delivery_residuals_stdout.log`

It does not read Telegram tokens, send Telegram messages, change LaunchAgents, mutate the production DB, edit workbooks, edit Google Sheets, or touch marketplace systems.

## Status Semantics

- GREEN: every configured job has scheduled-run evidence for every required date in the window, the current as-of time is after the cutoff, and no configured skipped-alert text appears in the window.
- ARMED: no skipped-alert regression is found, but the elapsed window is not mature or scheduled-run evidence is still missing.
- RED: a skipped-alert regression appears inside the window, a required log is missing, or the report cannot evaluate the configured proof surface.

## Current Window

The accepted repair-start date is `2026-06-13`. With a seven-day window, the first promotable day is after the `2026-06-19` scheduled runs and after the configured post-EOD cutoff.

This report is evidence only. It cannot itself promote final acceptance while other hard gates remain non-GREEN.
