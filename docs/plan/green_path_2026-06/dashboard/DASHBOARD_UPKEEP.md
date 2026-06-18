# Live Progress Dashboard — Orchestrator Upkeep Handout

The Green-Path program now has a **live progress dashboard**. The owner keeps it open and watches it. Keeping it current is part of running the program — not optional. This is short by design.

---

## ▶ COPY-PASTE PROMPT (give this to the new orchestrator)

> **MANDATORY LIVE DASHBOARD.** A progress dashboard tracks this program and the owner watches it; keeping it current is part of your job, not optional.
> - **Files** (workspace, canonical): `…/_workspaces/2026-06-12_green_path/dashboard/dashboard.html` (the renderer) + `progress-data.js` (the data). The owner keeps `dashboard.html` open; it auto-refreshes every ~15s.
> - **You edit ONLY `progress-data.js`** (the `window.GP` object). **NEVER edit `dashboard.html`.** A status flip is one clean find/replace.
> - **Update it in the SAME step** you touch `green_path_run/scoreboard.csv` / `STATUS.md` — they must never disagree.
> - **Triggers:** gate status change → flip that gate's `status`; phase boundary → set `current_phase` + that phase's `status`; take boundary → set `current_take` + that take's `status`; lane dispatch & lane return → unshift an `activity` line (newest first, keep ≤20); run-state change → set `status` (`EXECUTING`|`PAUSED`|`BLOCKED`); and **ALWAYS bump `updated`** to now (ISO local, e.g. `2026-06-14T09:05:00+05:00`).
> - **Status vocabulary ONLY:** `GREEN ARMED PARTIAL RED PENDING WAIVED OFF`. Every number on the page is *derived* — you only flip statuses.
> - **NEVER** put secrets, tokens, message contents, or customer PII in the data.
> - If the page shows a ⚠ **STALE** badge while `EXECUTING`, you forgot to update — fix it.
> - On resume: **re-baseline gate states from `scoreboard.csv` first**, then keep the dashboard live for the rest of the program.

---

## Where it lives

- **Canonical (edit here):** `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/dashboard/`
  - `dashboard.html` — the renderer (never edit)
  - `progress-data.js` — the single source you edit (`window.GP`)
  - `build_seed.py` — one-shot seed builder (re-run only to rebuild from `green_gates.csv`; **not** part of the edit loop)
- **Repo mirror:** `…/Docs/Autonomous_business/docs/plan/green_path_2026-06/dashboard/` — rides the existing milestone mirror; you don't maintain it per-edit.

## How to open it

- **Zero setup:** double-click `dashboard.html`. It runs fully offline and reloads itself ~15s (scroll preserved).
- **Smoothest (optional):** `cd dashboard && python3 -m http.server 8899`, then open `http://localhost:8899/dashboard.html` — updates hot-swap with no reload flicker.
- Press **`r`** to refresh now.

## What you edit — worked example

Flip one gate when its lane verifies (this is the whole maintenance loop):

```js
// before
{ "id": "G-ORD-01", "phase": 2, "group": "orders", "type": "HARD", "status": "PENDING" },
// after
{ "id": "G-ORD-01", "phase": 2, "group": "orders", "type": "HARD", "status": "GREEN" },
```

Then bump the stamp and log it:

```js
"updated": "2026-06-14T11:20:00+05:00",
// activity (newest first, keep ≤ 20):
{ "ts": "2026-06-14T11:20+05", "text": "PKT-LINES applied — 657-order entries hole backfilled; G-ORD-01 GREEN" },
```

The ring %, the "HARD remaining" count, and the Phase-2 bar all update on the next refresh — you never touch those.

## When to update (the trigger ritual)

| Moment | Edit in `progress-data.js` |
|---|---|
| A gate verifies / regresses | flip that gate's `status` |
| You dispatch a lane / a lane returns | unshift an `activity` line (≤20) |
| You cross a phase boundary | set `current_phase` + that phase's `status` (`done`/`active`) |
| You cross a take boundary | set `current_take` + that take's `status` |
| You pause / get blocked / resume | set top-level `status` |
| **Every** edit | bump `updated` to now |

Bundle this into the same moment you already update `scoreboard.csv` / `STATUS.md`. The dashboard is the **visual mirror** of those records; if they ever disagree, the records win — fix the dashboard.

## Gate status meanings (fixed vocabulary)

| status | meaning | counts as green? |
|---|---|---|
| `GREEN` | verified pass | ✅ yes |
| `WAIVED` | owner-waived (advisory or accepted) | ✅ yes |
| `OFF` | deliberately governed-OFF (e.g. auto-PO) = intended end state | ✅ yes |
| `ARMED` | mechanism in place; standing window not yet closed | ⏳ no (in progress) |
| `PARTIAL` | partially passing / blocked on data | ⏳ no (in progress) |
| `RED` | failing / not done | ❌ no |
| `PENDING` | not started | ❌ no |

## Rules / don'ts

- Edit **only** `progress-data.js`. Renderer changes (new visual concept) are a **Fable** task — ask the owner; don't hand-edit the HTML.
- Keep it **valid JS** (one `window.GP = { … };` object literal). If you break the syntax the page shows the "no data" state — re-check your edit.
- **No secrets / tokens / message-ids / customer PII**, ever. Activity lines describe gate/lane events only.
- Use the **fixed status vocabulary** only — the colors and counts depend on it.
- Don't hardcode numbers anywhere; they're all derived from `gates`.

## Stale guard

While `status:"EXECUTING"`, if `updated` is older than ~20 min the page shows a ⚠ **STALE** badge — your cue that you fell behind. While `PAUSED` it stays calm (no alarm). On the next resume, set `status:"EXECUTING"` and keep the stamp fresh.
