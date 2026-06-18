# G-ACC-01 Final Acceptance Gate Contract

Gate: `G-ACC-01`

Purpose: publish the final scored gate matrix for the green-path program without allowing a false completion claim.

Authority:
- Gate definitions come from `docs/plan/green_path_2026-06/green_gates.csv`.
- Current gate state comes from `docs/plan/green_path_2026-06/dashboard/progress-data.js`.
- `scoreboard.csv` supplies evidence text and dated rows, but the dashboard status is the current-state authority.
- `DEFERRED_QUEUE.md` must be empty or every row must carry a fallback/unblock policy.
- Owner signoff must be recorded in the configured signoff artifact before the gate can be green.

Scoring:
- Every `HARD` gate except the acceptance gate itself must be `GREEN`.
- Every `ADVISORY` gate must be `GREEN` or `WAIVED`.
- Acceptance must be scored after the post-EOD acceptance window, default `21:10` Asia/Almaty.
- The acceptance gate is `GREEN` only when all matrix, queue, timing, and owner-signoff requirements pass. Otherwise it is `RED`.

Safety:
- This contract is read-only. It must not write the production DB, workbook, Google Sheet, Telegram, Kaspi merchant, Repricer, pricing, stock, customer/operator message, LaunchAgent, or any external system.
