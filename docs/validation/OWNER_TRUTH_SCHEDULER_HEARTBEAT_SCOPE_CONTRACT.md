# Owner Truth Scheduler Heartbeat Scope Contract

## Purpose

Define whether `validate_scheduler_heartbeat.py` is part of strict owner-truth doctor by default.

## Decision

- default owner-truth doctor scope: exclude scheduler heartbeat
- opt-in scope: include scheduler heartbeat only when `AB_INCLUDE_SCHEDULER_HEARTBEAT=1`

## Rationale

- owner-truth live proving validates direct publication truth and direct daily owner outputs
- `validate_scheduler_heartbeat.py` proves launchd/runtime scheduler execution via repo-local stdout logs
- those heartbeat logs are owned by scheduler proving and H5 operational proving, not by direct owner-truth publication runs

## Hard rules

- owner-truth doctor must not fabricate missing runtime logs
- excluding scheduler heartbeat by default must not weaken the dedicated scheduler or H5 proving path
- any workflow that explicitly owns scheduler-runtime proving must enable it with `AB_INCLUDE_SCHEDULER_HEARTBEAT=1`

## Operational effect

- `system_doctor.py --strict` defaults to owner-truth publication scope
- scheduler-runtime proving continues to use `validate_scheduler_heartbeat.py --strict` directly
- H5 operational proving still requires `scheduler_heartbeat.json` and must opt into the heartbeat validator explicitly
