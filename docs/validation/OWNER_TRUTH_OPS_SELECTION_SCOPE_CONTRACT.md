# Owner Truth Ops-Selection Scope Contract

## Purpose

Define whether `validate_ops_selection_parity.py` is part of strict owner-truth doctor by default.

## Decision

- default owner-truth doctor scope: exclude ops-selection parity
- opt-in scope: include ops-selection parity only when `AB_INCLUDE_OPS_SELECTION_PARITY=1`

## Rationale

- owner-truth live proving is blocked or unblocked by current publication truth, not by whether the import scheduler log exists
- `validate_ops_selection_parity.py` depends on canonical scheduler runtime logs such as `runtime_logs/kaspi_import_stdout.log`
- those logs are owned by the import/daily-ops workflow, not by owner-truth publication itself

## Hard rules

- owner-truth doctor must not fabricate missing runtime logs
- skipping ops-selection parity by default must not weaken the dedicated scheduler proving path
- any workflow that explicitly owns import selection parity must enable it with `AB_INCLUDE_OPS_SELECTION_PARITY=1`

## Operational effect

- `system_doctor.py --strict` defaults to owner-truth publication scope
- scheduler or daily-ops proving can opt into the parity check explicitly
- direct parity failures remain valid evidence, but they are not default owner-truth release blockers
