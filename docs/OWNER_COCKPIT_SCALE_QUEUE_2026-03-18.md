# Owner Cockpit Scale Queue — 2026-03-18

## Stable center
- Released green center remains `2026-03-09`.
- Profit semantics: fail-closed blocked, not widened.
- Planning freshness: fail-closed blocked, not widened.
- Scheduler/import strict path: proven.
- Multi-day autonomy: not reproved; historical `2026-03-08` stopline remains red.

## Queue order
1. Stock snapshot freshness closure
- Why: this is the highest remaining owner-facing operational blind spot.
- Gate: prove a canonical post-`2026-03-09` stock snapshot path before any freshness wording changes.

2. Profit publication-grade unlock
- Why: value unlock is high, but only after publication semantics are backed by contract-level evidence.
- Gate: lift month/store `decision_grade` only through contract + validator evidence, never by wording.

3. Historical on-delivery freeze remediation
- Why: this blocks multi-day autonomy reproving.
- Gate: repair or explicitly quarantine historical balances with auditable evidence.

4. Broader cashflow / PO / inventory module reactivation
- Why: only after the stable center and freshness semantics are honest and reproducible.
- Gate: each module must carry its own READCHECK, DoD, and rollback story.

## Explicit deferrals
- Do not reopen scheduler/import mutation flows; proving is done.
- Do not widen owner profit semantics by report-layer wording.
- Do not represent stale planning as fresh.
