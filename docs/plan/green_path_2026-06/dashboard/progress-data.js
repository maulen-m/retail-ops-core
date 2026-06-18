window.GP = {
  "program": "Green-Path — Kaspi ops to 100% green",
  "updated": "2026-06-18T20:49:26+05:00",
  "status": "BLOCKED",
  "current_phase": 3,
  "current_take": 2,
  "note": "G-DARK-01 remains RED after no-write preflight: RUSH_WHITE S/M/3XL exact rows missing from ACTIVE/ARCHIVE; queue has 0 dispatch-ready items.",
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
      "status": "ARMED"
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
      "status": "RED"
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
      "time": "2026-06-18T20:49:26+05:00",
      "text": "G-DARK-01 RED no-write: RUSH_WHITE S/M/3XL rows missing from ACTIVE/ARCHIVE; T-SHIRT_BLACK L archive candidates found; OA-DARK01 waits owner."
    },
    {
      "time": "2026-06-18T20:40:07+05:00",
      "text": "G-DARK-01 dispatch: fresh Kaspi ACTIVE/ARCHIVE preflight for exact RUSH_WHITE relist/off switch; no upload before safe dry-run proof."
    },
    {
      "time": "2026-06-18T20:34:48+05:00",
      "text": "G-PRICE-03 RED refresh: LINE floor authority executed; missing-floor rows are 0, under-floor units are 45, OA-DARK01 remains dispatch-ready."
    },
    {
      "time": "2026-06-18T20:30:48+05:00",
      "text": "Resume: owner-action queue verified ARMED; OA-PRICE03-LINE and OA-DARK01 dispatch-ready; unresolved owner/fact/time items remain waiting."
    },
    {
      "time": "2026-06-18T19:44:02+05:00",
      "text": "Owner-action validator + recorder + starter pack published and mirrored; queue is ARMED but dispatch-blocked."
    },
    {
      "time": "2026-06-18T19:35:37+05:00",
      "text": "Owner-action queue published: 7 approval/fact/time items tied to remaining RED/ARMED/PARTIAL gates."
    },
    {
      "time": "2026-06-18T19:35:37+05:00",
      "text": "G-DARK-01 rechecked with fresh 19:30 Repricer source; RED mismatch unchanged."
    },
    {
      "time": "2026-06-18T19:30:56+05:00",
      "text": "BLOCKED: next-owner-actions packet written; remaining blockers require exact approvals, real QC/cash facts, or elapsed time."
    },
    {
      "time": "2026-06-18T19:27:50+05:00",
      "text": "G-SCHED-02 PARTIAL refresh: 15 settlement rows applied with backup; validate_params PASS; cash freshness/floor still block EOD."
    },
    {
      "time": "2026-06-18T19:26:20+05:00",
      "text": "G-SCHED-02 apply dispatch: 15 on-delivery settlement rows, backup-first env-gated DB-only repair."
    },
    {
      "time": "2026-06-18T19:23:37+05:00",
      "text": "Triage dispatch: classify remaining acceptance blockers and probe only safe local/read-only lanes."
    },
    {
      "time": "2026-06-18T19:21:27+05:00",
      "text": "G-ACC-01 RED: final acceptance matrix published; hard/advisory blockers and owner signoff requirements are explicit."
    },
    {
      "time": "2026-06-18T19:13:18+05:00",
      "text": "G-DARK-02 ARMED: baseline published; recovery slope waits on G-DARK-01 and 30 mature post-relist days."
    },
    {
      "time": "2026-06-18T19:10:35+05:00",
      "text": "G-DARK-01 RED: RUSH_WHITE S/M/3XL missing buyable offers while excluded L is buyable."
    },
    {
      "time": "2026-06-18T19:06:25+05:00",
      "text": "G-MET-02 refreshed: cadence blockers are now ARMED evidence, not missing reports."
    },
    {
      "time": "2026-06-18T19:05:44+05:00",
      "text": "G-LIQ-03 refreshed: release velocity now reflects G-LIQ-02=ARMED; active tranche rows remain 0."
    },
    {
      "time": "2026-06-18T19:05:02+05:00",
      "text": "G-LIQ-02 ARMED: prior-canonical tranche-1 readiness row file published; execution still blocked by WA/price stoplines."
    },
    {
      "time": "2026-06-18T18:58:17+05:00",
      "text": "G-PO-03 ARMED: forecast accuracy loop report published; old WMAPE/MAPE/signed-bias evidence blocks GREEN."
    },
    {
      "time": "2026-06-18T18:52:56+05:00",
      "text": "G-PO-02 ARMED: PO size-prior report published; dashboard invariants pass but return QC and stale/high-error forecasts block GREEN."
    },
    {
      "time": "2026-06-18T18:46:26+05:00",
      "text": "G-LIQ-03 ARMED: release-velocity discipline report published; 0 active tranche rows, 0 violations, G-LIQ-02 pending."
    }
  ]
};
