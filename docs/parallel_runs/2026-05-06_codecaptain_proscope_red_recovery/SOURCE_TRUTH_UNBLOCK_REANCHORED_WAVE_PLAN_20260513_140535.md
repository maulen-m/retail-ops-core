# Source Truth Unblock Reanchored Wave Plan - 2026-05-13 14:05:35 +0500

Gate: GREEN_TO_LAUNCH_REVIEW_ONLY_REANCHORED_SOURCE_WAVE

## Purpose

Launch the fastest safe follow-up wave after the `7cfe...` to `04c764...` DB drift was reclassified as SQLite header/schema-cookie drift only.

This wave is allowed to proceed without another human approval under the owner directive recorded in:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_DRIFT_FORENSICS_AND_READONLY_HARDENING_20260513_140535.md`

## Active Boundary

- DB: `~/Docs/Autonomous_business/db/app.db`
- DB SHA256: `04c76434399eb7e146037271fa121d69f71ae64195ac5a3436ccfed080b18f99`
- DB mtime: `2026-05-13T12:21:48+0500`
- DB integrity: `ok`
- Workbook: `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- Workbook SHA256: `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`
- Workbook mtime: `2026-05-12T17:06:10+0500`

This boundary is review-only. It does not authorize production apply, owner publication, workbook mutation, scheduler restore, or external writes.

## Parallel Execution

All five agents launch in parallel under group `source_truth_reanchored_wave`.

- Agent793: cashflow source truth and missing-cost unblock packet.
- Agent794: stock/order identity-bearing order-entry source capture/proof packet.
- Agent795: ads source capture/adoption packet using local evidence plus bounded read-only source methods.
- Agent796: PO inbound fresh source decision and copied-temp feasibility packet.
- Agent797: exception owner/source fact resolution packet for open high controls.

## Shared Rules

- First verify the active `04c764...` DB and `4e7...` workbook boundary.
- If the boundary no longer matches, stop and close out `RED`.
- Allowed writes are limited to assigned evidence folders, assigned closeout files, and copied DBs inside assigned evidence folders.
- Production DB and workbook must not be mutated.
- Scheduler, LaunchAgent, plist, cron, and automation restore/mutation are forbidden.
- External writes are forbidden.
- Owner publication and owner approval requests are forbidden.
- Cash movement, supplier payment, PO commitment, ad spend, price changes, and stock changes are forbidden.
- Read-only source capture is allowed only when the command/tool is clearly non-mutating and writes evidence locally.
- If a source path requires login/2FA ambiguity, credential/session export, or any write-risk UI action, stop `YELLOW` with the exact required next command or source requirement.

## Success Condition

The wave is successful if each blocker domain produces either:

- a `GREEN` artifact-backed source packet or copied-temp proof that can be consumed by the next validation lane, or
- a precise `YELLOW` stopline identifying the smallest missing owner/source fact, command, or input.

Any forbidden write risk, boundary mismatch, or unverifiable source mutation risk must close `RED`.
