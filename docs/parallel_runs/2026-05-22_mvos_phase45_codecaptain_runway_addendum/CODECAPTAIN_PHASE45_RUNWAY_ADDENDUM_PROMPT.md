# CodeCaptain Phase45 Runway Addendum Prompt

Please review this as a small addendum to the existing Autonomous_business Phase42 non-production MVOS review packet:

`~/Docs/Oracle/Autonomous_business/2026-05-22/062954_TASK-000_mvos-phase42-codecaptain-review-pack-refresh`

This addendum does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, production apply, copied DB creation, or evidence deletion.

## Why This Addendum Exists

After Phase42, the next copied-temp MVOS proof wave became blocked by disk runway. The current repo run root has far less than the required copied-temp DB runway.

Current live stopline:

- combined copied-temp preflight fails with `FAIL_LOW_DISK_RUNWAY`;
- free space is approximately `0.175 GiB`;
- first cleanup batch dry-run is clean: `16` eligible copied DB artifacts, `0` blocked, approximately `3920.0 MiB` recoverable if owner approves deletion;
- DB guard passes;
- source-contract registry passes;
- copied DB helper dry-run refuses copy because `required_free_before_copy=3477786624` bytes while current free space is only about `0.175 GiB`.

## New Local Guardrails

- `scripts/preflight_copied_temp_wave.py` now supports `--run-root <existing-path>`.
- `scripts/check_validation_disk_runway.py` fails closed if the selected run root does not exist.
- `scripts/create_copied_temp_db.py` is a dry-run-first copied DB helper that:
  - requires an existing run root;
  - checks runway before copying;
  - requires enough free space for the minimum runway plus the source DB size;
  - refuses path escapes;
  - records source and target SHA-256;
  - runs SQLite `PRAGMA integrity_check`;
  - only creates a DB when `--copy` is explicit.

## Requested Decision

Please return a decision-grade answer with:

- `GREEN` / `YELLOW` / `RED` for this runway/restart addendum.
- Whether Phase43 owner-approved cleanup is the correct next unblocker.
- Whether future copied-temp waves should require `create_copied_temp_db.py` instead of ad hoc DB copy commands.
- Whether the minimum free-space gate should be `3 GiB` or stricter `8-10 GiB`.
- Whether production-preflight discussion must stay blocked until a new copied-temp proof passes under this run-root gate.
- Any exact owner approval phrase needed for local evidence cleanup or for using an alternate run root, if different from the Phase43 phrase.
