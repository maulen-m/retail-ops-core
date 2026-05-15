# Agent808 - Clean DB Order-Entry Owner Request Packet Refresh

You are Agent808 in `~/Docs/Autonomous_business`.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_db_order_entry_owner_request_clean/agent808_clean_owner_request_packet_closeout.md`

## Mission

Create a clean, owner-ready candidate packet for DB-only order-entry recovery by rerunning the current-boundary proof without Agent807's process-boundary deviation.

This is still packet/preflight work only. Production DB apply remains blocked.

## Required Reading

Read:

1. `AGENTS.md`
2. `docs/00_START_HERE.md`
3. `.claude/OPERATING.md`
4. `docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_CURRENT_426_419_0_OWNER_REQUEST_PREP_20260514.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-14/211726_TASK-000_db-order-entry-apply-contract-review-current-426-419-0/answer/Code Captain_14.05.2026_21_30_19.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_db_order_entry_owner_request/agent807_owner_approval_request_packet_closeout.md`
7. `exports/validation/db_order_entry_owner_approval_request/20260514_214106_agent807_current_reconfirm/RUN_STATUS.json`
8. `exports/validation/db_order_entry_owner_approval_request/20260514_214106_agent807_current_reconfirm/OWNER_DB_ORDER_ENTRY_RECOVERY_APPROVAL_REQUEST_PACKET.md`

## Hard Boundary

Allowed:

- read-only current-boundary checks;
- strict dry-run without `--apply`;
- evidence packet writing under `exports/validation/db_order_entry_owner_approval_request/`;
- Oracle/CodeCaptain-style packet writing under `~/Docs/Oracle/Autonomous_business/2026-05-14/`;
- closeout writing to the assigned closeout path.

Forbidden:

- no production DB apply;
- no `--apply`;
- no DB write-enable env gate;
- no protected workbook mutation;
- no scheduler/LaunchAgent/plist/cron mutation;
- no Web_automation mutation;
- no browser/login automation or credential/session export;
- no external writes;
- no owner publication;
- no asking the owner for the phrase;
- no cash, PO, ads, price, or stock changes;
- no lifecycle/status repair;
- no treating manual WebUI archive as recovery source hierarchy.

## Critical Difference From Agent807

Do **not** run:

```bash
python3 scripts/manage_business_automation.py verify ...
```

That command creates its own report directory under `exports/automation_control/`, which caused Agent807's RED process-boundary deviation.

Use this instead:

```bash
python3 scripts/manage_business_automation.py status --scope all-business --json --output-json <your_evidence_root>/business_automation_status_all_business.json
```

Then explicitly inspect that status JSON for:

- `ok=true`
- `loaded_count=0`
- `cron.has_entries=false`
- no protected-surface open handles
- no SQLite sidecars

Also capture direct `lsof`, sidecar, and cron checks. Before and after the run, snapshot `find exports/automation_control/2026-05-14 -maxdepth 1 -type d` and prove no new automation-control run directory was created by this clean lane.

## Expected Contract

- DB SHA: `09198109d63611ee1de120d6168ffcadb4195f84dbabe39215ddb969e332440a`
- Workbook SHA: `eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`
- DB integrity: `ok`
- Strict dry-run: `426` would-insert rows, `419` target order-store pairs, `0` quarantine rows
- Source hierarchy: `API_RAW_ORDER_ENTRIES` only
- `inserted_entry_rows=0`
- `production_db_modified=false`
- `workbook_sources_used=false`
- `webui_archive_sources_used=false`
- `entry_candidates.non_api_entry_rows=0`

Create a timestamped evidence root like:

`exports/validation/db_order_entry_owner_approval_request/20260514_<HHMMSS>_agent808_clean_status_only/`

Reuse the Agent807 dry-run command shape with only `--output-root` changed to your evidence root's `dry_run/`. Do not add `--apply`.

## Packet To Build

Build the clean owner approval request packet with the same CodeCaptain-approved inert phrase.

Important:

- Phrase text remains inert review text until the owner later sends it exactly in the correct launch context.
- Do not claim production apply is authorized.
- Do not ask the owner for the phrase.
- Keep lifecycle/status caveat separate.
- Keep manual WebUI archive as corroboration only.

Suggested Oracle pack:

`~/Docs/Oracle/Autonomous_business/2026-05-14/<HHMMSS>_TASK-000_db-order-entry-owner-approval-request-packet-clean/`

## Gate Rules

Close `GREEN` only if:

- DB/workbook hashes match expected;
- integrity is `ok`;
- all-business status is quiet using status-only evidence and direct checks;
- no new automation-control run directory is created by this lane;
- dry-run matches `426 / 419 / 0`;
- no production mutation indicators appear;
- packet preserves all non-authorizations and caveats.

Close `YELLOW` if the packet is useful but there is a minor review-only uncertainty.

Close `RED` if any production mutation happened, the dry-run contract fails, or another out-of-scope write appears.

Your closeout must include:

- READCHECK;
- commands run;
- files created;
- gate result;
- exact reason if not GREEN;
- next human/orchestrator action;
- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
