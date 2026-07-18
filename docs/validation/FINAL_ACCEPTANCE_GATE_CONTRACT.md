# G-ACC-01 Final Acceptance Gate Contract

Gate: `G-ACC-01`

Purpose: publish the final scored gate matrix for the green-path program without allowing a false completion claim.

Authority:

- Gate definitions come from `docs/plan/green_path_2026-06/green_gates.csv`.
- Current gate state comes from `docs/plan/green_path_2026-06/dashboard/progress-data.js`.
- `scoreboard.csv` supplies evidence text and dated rows, but the dashboard status is the current-state authority.
- `DEFERRED_QUEUE.md` must be empty or every row must carry a fallback/unblock policy.
- Owner signoff must be recorded in the configured signoff artifact before the gate can be green.

Provenance and freshness:

- The dashboard and scoreboard publication timestamps must be present, parseable, non-future, and no more than the configured 24 hours old at the acceptance `as_of` time.
- Freshness comes from the source-declared timestamps. Filesystem mtime is never a fallback.
- The scoreboard publication timestamp is the `dated` value on its final physical data row. A malformed newest row fails closed even if older rows are parseable.
- The dashboard must be in a configured terminal status: `READY_FOR_ACCEPTANCE` or `COMPLETE`. `EXECUTING` cannot be accepted.
- Dashboard gate identities must match the gate matrix.
- The scoreboard must contain every matrix gate ID. Extra rows may be reported, but missing matrix IDs block acceptance.
- Dashboard and scoreboard states must agree for every covered matrix gate. The dashboard remains the scoring authority, but disagreement blocks acceptance until reconciled.
- Every accepted gate other than `G-ACC-01` must have nonblank scoreboard evidence and a parseable, non-future `dated` value. Accepted means `GREEN` for a hard gate or a configured allowed status such as `GREEN`/`WAIVED` for an advisory gate.
- Raw dashboard and scoreboard gate states must be recognized values. Unknown or explicit `MISSING` states fail closed, including for `G-ACC-01`.
- These global source checks are necessary but do not replace any stricter per-gate `freshness_sla` in the gate matrix. A leading `Nd` duration is enforced as `N * 24` hours, `continuous...` is enforced as 24 hours, and `n/a` has no age cap. Event-based values such as `per change`, `per write`, `per apply`, `per upload`, and `until count done` fail closed until a dedicated evaluator exists.
- The configured operational-as-of limit defaults to 24 hours. A replay whose `as_of` is older than that relative to evaluation time is labelled `HISTORICAL_REPLAY` and cannot issue operational `GREEN`, even if its historical inputs reconcile.

Scoring:

- Every `HARD` gate except the acceptance gate itself must be `GREEN`.
- Every `ADVISORY` gate must be `GREEN` or `WAIVED`.
- Acceptance must be scored after the post-EOD acceptance window, default `21:10` Asia/Almaty.
- The acceptance gate is `GREEN` only when all provenance, freshness, matrix, queue, timing, and owner-signoff requirements pass. Otherwise it is `RED`.

Safety:

- This contract is read-only. It must not write the production DB, workbook, Google Sheet, Telegram, Kaspi merchant, Repricer, pricing, stock, customer/operator message, LaunchAgent, or any external system.
- Reporter artifacts must be written to an explicit isolated output root during audits or tests.
