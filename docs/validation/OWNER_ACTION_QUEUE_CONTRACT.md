# Owner Action Queue Contract

Purpose: keep the remaining green-path owner approvals, real-world facts, and elapsed-window items machine-readable and fail-closed.

This contract does not authorize any live write. It only validates that the next-action queue is explicit enough for later execution agents to consume without guessing.

## Inputs

- Queue JSON: `exports/validation/g_acc01_final_acceptance/20260618_192023_0500/owner_action_queue.json`
- Queue CSV: `exports/validation/g_acc01_final_acceptance/20260618_192023_0500/owner_action_queue.csv`
- Config: `config/validation/owner_action_queue.json`

## Required Checks

- JSON and CSV action IDs match exactly.
- Every action has a `gate_ids`, `kind`, `status`, `surface`, and `artifact`.
- Every referenced local artifact exists.
- Approval actions include explicit forbidden-surface language before they can be dispatched.
- Status values are from the allowed set in config.
- Dispatch remains blocked while statuses are `WAITING_OWNER`, `WAITING_REAL_FACT`, `WAITING_OWNER_OR_SOURCE`, or `WAITING_TIME`.

## Semantics

- `GREEN`: queue is valid and no waiting actions remain.
- `ARMED`: queue is valid and waiting actions remain.
- `RED`: queue is invalid or unsafe to consume.

This contract must not write production DB, workbook, Google Sheet, Telegram, Kaspi merchant, Repricer, pricing, stock, customer/operator messages, LaunchAgents, cash, PO, or other external systems.
