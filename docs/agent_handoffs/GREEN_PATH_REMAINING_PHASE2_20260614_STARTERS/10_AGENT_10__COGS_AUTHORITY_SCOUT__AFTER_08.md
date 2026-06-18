# Agent 10 - COGS Authority Scout After Residual Settlement

You are Agent 10 in the green-path Phase 2 run.

Repo: `~/Docs/Autonomous_business`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent10_cogs_authority_scout_closeout.md`

## Scope

Read-only scout for remaining COGS/profit authority blockers after cash anchor and residual-settlement progress.

Current accepted DB boundary:

- `db/app.db` SHA256: `2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`

Known prior finding:

- Agent2 found one current publication blocker: order `953395459`, sale `2026-06-11`, store `ACMEWEAR`, SKU `LINE-31-LS_XL`, unresolved COGS.
- Existing authority scan said `LINE-31-LS` did not have a current accepted production COGS inheritance contract at that time.

## Must Read

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
- `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent2_cogs_fx_profit_scout_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent5_serial_write_integrator_closeout.md`
- Relevant COGS authority docs/contracts under `docs/parallel_runs/`, `docs/inventory/`, `docs/protocol/active/`, and tests/scripts referenced by the closeouts.
- `scripts/validate_profit_publication_integrity.py`
- `scripts/validate_cogs_completeness_by_month.py`
- `scripts/audit_cogs_realism.py`
- `scripts/validate_cogs_realism_vs_forensic.py`

## Forbidden

- No DB writes, no `--apply`, no env-gated writes.
- Do not edit dashboard, scoreboard, STATUS, Oracle workspace mirror, code, plists, LaunchAgents, Telegram, Kaspi, Repricer, browser, workbook, pricing, stock, returns, cash, or customer/operator-message surfaces.
- Do not create a COGS contract or authority doc; only report whether an existing accepted authority exists or exactly what authority is missing.

## Required Work

1. Verify the DB SHA starts at `2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`.
2. Re-run the smallest current read-only profit/COGS diagnostics needed to identify current blockers:
   - current publication integrity,
   - current COGS completeness for recent/current period,
   - relevant COGS realism checks.
3. For each blocker, classify:
   - exact order/SKU/store/date,
   - whether SKU identity is known,
   - whether a current accepted COGS source/contract exists,
   - whether a pre-approved script can apply it,
   - whether owner authority is still missing.
4. Pay special attention to `LINE-31-LS_XL` and whether the user's later compatibility note about suit/nike 3-in-1 and kids S sizes changes nothing or changes authority. Do not infer a LINE COGS contract from unrelated compatibility notes unless the repo evidence supports it.
5. Recommend the next move:
   - safe writer prompt if existing authority is sufficient,
   - or a compact owner-authority phrase / contract draft needed before a writer can run,
   - or a park decision with quantified blocker impact.

## Closeout Gate

Use:

- `Gate: GREEN` if the read-only classification is complete and the next step is unambiguous.
- `Gate: YELLOW` if authority is missing or ambiguous.
- `Gate: RED` only if you discover data loss, an unexpected post-Agent8 regression, or a live safety issue.

Closeout must include a standalone line: `Gate: <GREEN/YELLOW/RED>`.

