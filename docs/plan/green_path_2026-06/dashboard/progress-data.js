window.GP = {
  "program": "Green-Path — Kaspi ops to 100% green",
  "updated": "2026-06-19T21:37:50+05:00",
  "status": "BLOCKED",
  "current_phase": 5,
  "current_take": 3,
  "note": "Final acceptance rechecked after advisory refresh: counts unchanged at GREEN 51, ARMED 15, PARTIAL 2, RED 3; owner facts/policy/strategy/signoff remain.",
  "takes": [
    {
      "id": 1,
      "label": "Take 1 · Phase 2 — Make the books true",
      "status": "active"
    },
    {
      "id": 2,
      "label": "Take 2 · Phases 3–4 — Money & durability",
      "status": "active"
    },
    {
      "id": 3,
      "label": "Take 3 · Phase 5 — Acceptance",
      "status": "active"
    }
  ],
  "phases": [
    {
      "id": -1,
      "title": "Save the game",
      "purpose": "Backup, freeze, restore-test before any write.",
      "status": "done"
    },
    {
      "id": 0,
      "title": "Check the tools",
      "purpose": "Dry-run inventory, go/no-go table, rollback rehearsals.",
      "status": "done"
    },
    {
      "id": 1,
      "title": "Restore the pulse",
      "purpose": "Scheduler repair, alerting revival, offsite backup.",
      "status": "done"
    },
    {
      "id": 2,
      "title": "Make the books true",
      "purpose": "Entries, COGS, FX, cash, stock, returns, ads, quarantine, residuals.",
      "status": "active"
    },
    {
      "id": 3,
      "title": "Turn truth into money",
      "purpose": "Floors, leak-stop, relists, liquidation tranche-1, storefront.",
      "status": "active"
    },
    {
      "id": 4,
      "title": "Make it stay fixed",
      "purpose": "PO governance, PPCH v1, telemetry, weekly digest, watchdog.",
      "status": "active"
    },
    {
      "id": 5,
      "title": "Final inspection",
      "purpose": "Score all 71 gates, owner acceptance.",
      "status": "active"
    }
  ],
  "gates": [
    {
      "id": "G-BCK-01",
      "phase": -1,
      "group": "backup",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-BCK-02",
      "phase": -1,
      "group": "backup",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-BCK-03",
      "phase": -1,
      "group": "backup",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-BCK-04",
      "phase": 1,
      "group": "backup",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RDY-01",
      "phase": 0,
      "group": "readiness",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RDY-02",
      "phase": 0,
      "group": "readiness",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RDY-03",
      "phase": 0,
      "group": "readiness",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RDY-04",
      "phase": 0,
      "group": "readiness",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-SCHED-01",
      "phase": 1,
      "group": "scheduler",
      "type": "HARD",
      "status": "PARTIAL"
    },
    {
      "id": "G-SCHED-02",
      "phase": 1,
      "group": "scheduler",
      "type": "HARD",
      "status": "PARTIAL"
    },
    {
      "id": "G-SCHED-03",
      "phase": 1,
      "group": "scheduler",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-SCHED-04",
      "phase": 2,
      "group": "scheduler",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-SCHED-05",
      "phase": 2,
      "group": "scheduler",
      "type": "ADV",
      "status": "GREEN"
    },
    {
      "id": "G-ALERT-01",
      "phase": 1,
      "group": "alerting",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ALERT-02",
      "phase": 1,
      "group": "alerting",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ORD-01",
      "phase": 2,
      "group": "orders",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ORD-02",
      "phase": 2,
      "group": "orders",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ORD-03",
      "phase": 2,
      "group": "orders",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ORD-04",
      "phase": -1,
      "group": "orders",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-COGS-01",
      "phase": 2,
      "group": "profit_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-COGS-02",
      "phase": 2,
      "group": "profit_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-COGS-03",
      "phase": 2,
      "group": "profit_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-COGS-04",
      "phase": 2,
      "group": "profit_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-FX-01",
      "phase": 2,
      "group": "fx_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-FX-02",
      "phase": 2,
      "group": "fx_cogs",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-CASH-01",
      "phase": 2,
      "group": "cash",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-CASH-02",
      "phase": 2,
      "group": "cash",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-CASH-03",
      "phase": 2,
      "group": "cash",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-CASH-04",
      "phase": 3,
      "group": "cash",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-STOCK-01",
      "phase": 2,
      "group": "stock",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-STOCK-02",
      "phase": 2,
      "group": "stock",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-STOCK-03",
      "phase": 2,
      "group": "stock",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-STOCK-04",
      "phase": 2,
      "group": "stock",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-STOCK-05",
      "phase": 2,
      "group": "stock",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RET-01",
      "phase": 2,
      "group": "returns",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-RET-02",
      "phase": 2,
      "group": "returns",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-RET-03",
      "phase": 3,
      "group": "returns",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-ADS-01",
      "phase": 2,
      "group": "ads",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ADS-02",
      "phase": 2,
      "group": "ads",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ADS-03",
      "phase": 2,
      "group": "ads",
      "type": "ADV",
      "status": "GREEN"
    },
    {
      "id": "G-QUAR-01",
      "phase": 2,
      "group": "quarantine",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-QUAR-02",
      "phase": 2,
      "group": "quarantine",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-QUAR-03",
      "phase": 2,
      "group": "quarantine",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-QUAR-04",
      "phase": 2,
      "group": "quarantine",
      "type": "ADV",
      "status": "GREEN"
    },
    {
      "id": "G-RESID-01",
      "phase": 2,
      "group": "residuals",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PRICE-01",
      "phase": 2,
      "group": "pricing",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PRICE-02",
      "phase": 3,
      "group": "pricing",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PRICE-03",
      "phase": 3,
      "group": "pricing",
      "type": "HARD",
      "status": "RED"
    },
    {
      "id": "G-PRICE-04",
      "phase": 2,
      "group": "pricing",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PRICE-05",
      "phase": 3,
      "group": "pricing",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-WA-01",
      "phase": 3,
      "group": "wa_pricing",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-WA-02",
      "phase": 3,
      "group": "wa_pricing",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-DARK-01",
      "phase": 3,
      "group": "relist",
      "type": "HARD",
      "status": "RED"
    },
    {
      "id": "G-DARK-02",
      "phase": 3,
      "group": "relist",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-LIQ-01",
      "phase": 3,
      "group": "liquidation",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-LIQ-02",
      "phase": 3,
      "group": "liquidation",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-LIQ-03",
      "phase": 3,
      "group": "liquidation",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-LIQ-04",
      "phase": 3,
      "group": "liquidation",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-STORE-01",
      "phase": 3,
      "group": "storefront",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-LINE31-01",
      "phase": 2,
      "group": "storefront",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PO-01",
      "phase": 3,
      "group": "po_gov",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-PO-02",
      "phase": 4,
      "group": "po_gov",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-PO-03",
      "phase": 4,
      "group": "po_gov",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-MET-01",
      "phase": 4,
      "group": "metrics",
      "type": "HARD",
      "status": "ARMED"
    },
    {
      "id": "G-MET-02",
      "phase": 4,
      "group": "metrics",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-MET-03",
      "phase": 4,
      "group": "metrics",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-MET-04",
      "phase": 4,
      "group": "metrics",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-OPS-01",
      "phase": 3,
      "group": "ops",
      "type": "ADV",
      "status": "ARMED"
    },
    {
      "id": "G-REPO-01",
      "phase": 0,
      "group": "repo_guards",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-REPO-02",
      "phase": 0,
      "group": "repo_guards",
      "type": "HARD",
      "status": "GREEN"
    },
    {
      "id": "G-ACC-01",
      "phase": 5,
      "group": "acceptance",
      "type": "HARD",
      "status": "RED"
    }
  ],
  "activity": [
    {
      "time": "2026-06-19T21:37:50+05:00",
      "text": "G-ACC-01 RED after advisory refresh: hard green 48/61, advisory 3/10, owner signoff missing; blocker map remains ARMED."
    },
    {
      "time": "2026-06-19T21:35:44+05:00",
      "text": "Advisory refresh: G-RET-03, G-DARK-02, G-PO-02, G-PO-03, G-LIQ-03, G-MET-02, and G-OPS-01 remain ARMED; no external write."
    },
    {
      "time": "2026-06-19T21:30:57+05:00",
      "text": "G-ACC-01 RED refresh: counts GREEN 51, ARMED 15, PARTIAL 2, RED 3; elapsed waits cleared, remaining blockers are owner facts, policy, strategy, and signoff."
    },
    {
      "time": "2026-06-19T21:26:32+05:00",
      "text": "G-WA/G-LIQ/G-CASH refresh: G-PRICE-05 is no longer a LIQ blocker; G-WA-01, G-LIQ-02, G-LIQ-03, and G-CASH-04 remain ARMED with no external write."
    },
    {
      "time": "2026-06-19T21:21:33+05:00",
      "text": "G-SCHED-01 PARTIAL retained: scheduler contract clean, daily ops paused 0/10, heartbeat FAIL with 5 paused-window misses, and 10 loaded labels have nonzero exits."
    },
    {
      "time": "2026-06-19T21:13:18+05:00",
      "text": "G-ACC-01 RED refresh: counts GREEN 51, ARMED 15, PARTIAL 2, RED 3; hard green 48/61; alert elapsed window cleared, owner signoff and gate blockers remain."
    },
    {
      "time": "2026-06-19T21:12:29+05:00",
      "text": "G-ALERT-02 GREEN: 2026-06-13..2026-06-19 scheduled evidence is present for both alert jobs, skipped_alert_total=0, missing_evidence_count=0."
    },
    {
      "time": "2026-06-19T20:27:44+05:00",
      "text": "G-ALERT-02 ARMED: zero skipped-alert regressions found, but June 19 scheduled evidence for both jobs and the 21:10 cutoff are still missing."
    },
    {
      "time": "2026-06-19T20:24:31+05:00",
      "text": "EXECUTING G-ALERT-02 proof lane: adding read-only zero-skip window reporter and tests; no scheduler, Telegram, DB, marketplace, Google, or external write."
    },
    {
      "time": "2026-06-19T20:18:30+05:00",
      "text": "BLOCKED triage complete: remaining-blocker report ARMED with owner strategy 5, real facts 7, elapsed/cadence waits, and conservative cash-floor blocker."
    },
    {
      "time": "2026-06-19T20:05:54+05:00",
      "text": "BLOCKED checkpoint: no dispatch-ready queue items; daily ops paused 0/10; next safe proof waits elapsed alert/acceptance windows or owner facts/strategy decisions."
    },
    {
      "time": "2026-06-19T20:02:46+05:00",
      "text": "G-SCHED-02 PARTIAL refresh: EOD dry-run passes except cashflow PO preflight; base cash ok, conservative min cash 3668632.39 < floor 4234749.84."
    },
    {
      "time": "2026-06-19T19:57:48+05:00",
      "text": "G-ACC-01 RED refresh: counts GREEN 50, ARMED 16, PARTIAL 2, RED 3 after G-MET-04 repair; waits 21:10 and owner signoff."
    },
    {
      "time": "2026-06-19T19:55:52+05:00",
      "text": "G-MET-04 ARMED repair: cashflow daily rows refreshed through 2026-06-19 with guarded DB apply; strict params, integrity, and DB guard passed."
    },
    {
      "time": "2026-06-19T19:53:01+05:00",
      "text": "EXECUTING G-MET-04 repair: starting guarded cashflow calendar copied-DB proof for 2026-06-17..2026-06-19; no production write yet."
    },
    {
      "time": "2026-06-19T19:48:59+05:00",
      "text": "G-MET-04 RED refresh: fact_cashflow_daily latest date 2026-06-16, lag 3 > max 2; next is guarded calendar rebuild proof."
    },
    {
      "time": "2026-06-19T19:47:08+05:00",
      "text": "G-ACC-01 RED refresh: counts unchanged GREEN 50, ARMED 16, PARTIAL 2, RED 3; hard green 47/61 after metric refreshes."
    },
    {
      "time": "2026-06-19T19:45:43+05:00",
      "text": "G-MET-02 ARMED refresh: daily cadence 5/5 green; weekly/monthly wait on release velocity, returns, PPCH, PO, and 7-day history."
    },
    {
      "time": "2026-06-19T19:44:12+05:00",
      "text": "G-MET-01 ARMED refresh: PPCH v1 month-to-date now uses sales through 2026-06-19; waits on real return QC evidence."
    },
    {
      "time": "2026-06-19T19:42:31+05:00",
      "text": "G-MET-03 ARMED refresh: latest sales date 2026-06-19 lag 0; contribution rows 12; waits on return-loss and handling-cost sources."
    }
  ]
};
