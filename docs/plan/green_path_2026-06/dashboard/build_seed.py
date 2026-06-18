#!/usr/bin/env python3
"""One-shot SEED builder for the Green-Path progress dashboard.

Reads the authoritative green_gates.csv, applies the handoff-time status
overrides, and emits progress-data.js (the `window.GP` object the dashboard
renders). This is NOT part of the maintenance loop — after seeding, the
orchestrator hand-edits progress-data.js directly (flip a status string,
bump `updated`, push an activity line). Re-run only to rebuild from scratch.

Usage:
  python3 build_seed.py <path/to/green_gates.csv> <path/to/progress-data.js>

stdlib-only (csv/json/sys) — safe under any python3 incl. the dep-less brew 3.14.
No secrets / no PII are ever emitted.
"""
import csv
import json
import sys

# ---- handoff-time status overrides (everything else => PENDING) -------------
# Honest snapshot at the Phase-1/2 pause. The resuming orchestrator OWNS gate
# truth and should re-baseline these against scoreboard.csv on resume.
GREEN = {
    "G-BCK-01", "G-BCK-02", "G-BCK-03",   # Phase -1 backup complete (restore 3/3)
    "G-ORD-04",                            # order ingestion alive, validator exit 0
    "G-BCK-04",                            # offsite backup job live + spot-restore
    "G-ALERT-01",                          # Telegram forced-failure proof delivered
    "G-RDY-01", "G-RDY-02", "G-RDY-04",    # go/no-go + rollback rehearsals + single-writer in force
}
ARMED = {
    "G-ALERT-02",   # 7-day zero-skip window started
    "G-LINE31-01",     # satisfied-by-structure (AMD-11); standing cross-check arms in Phase 3
    "G-RDY-03",     # write-side gating designed; validator not yet run in-program
    "G-REPO-02",    # docs-before-code in force; validator pending
}
PARTIAL = {
    "G-SCHED-01",   # interpreter fixed; 9 jobs parked on Phase-2 DATA (not infra)
    "G-SCHED-02",   # EOD dry-run captured; apply blocked on data
    "G-REPO-01",    # lint_docs false-positive on "4,856,291"; pytest/db-tracked fine
}


def status_for(gid):
    if gid in GREEN:
        return "GREEN"
    if gid in ARMED:
        return "ARMED"
    if gid in PARTIAL:
        return "PARTIAL"
    return "PENDING"


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_seed.py <green_gates.csv> <progress-data.js>")
    src, out = sys.argv[1], sys.argv[2]

    gates = []
    with open(src, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = (row.get("gate_id") or "").strip()
            if not gid:
                continue
            blocking = (row.get("blocking") or "").strip().upper()
            gates.append({
                "id": gid,
                "phase": int((row.get("phase") or "0").strip()),
                "group": (row.get("domain") or "").strip(),
                "type": "ADV" if blocking.startswith("ADV") else "HARD",
                "status": status_for(gid),
            })

    gp = {
        "program": "Green-Path — Kaspi ops to 100% green",
        # ISO local time; the orchestrator bumps this on EVERY edit.
        "updated": "2026-06-13T13:47:00+05:00",
        "status": "PAUSED",            # EXECUTING | PAUSED | BLOCKED
        "current_phase": 2,            # -1,0,1,2,3,4,5
        "current_take": 1,             # 1,2,3
        "note": "Paused at Phase-1/2 boundary, handed off. Resume = Phase-2 first lane PKT-LINES.",
        "takes": [
            {"id": 1, "label": "Take 1 · Phase 2 — Make the books true", "status": "active"},
            {"id": 2, "label": "Take 2 · Phases 3–4 — Money & durability", "status": "pending"},
            {"id": 3, "label": "Take 3 · Phase 5 — Acceptance", "status": "pending"},
        ],
        "phases": [
            {"id": -1, "title": "Save the game",        "purpose": "Backup, freeze, restore-test before any write.",                              "status": "done"},
            {"id": 0,  "title": "Check the tools",       "purpose": "Dry-run inventory, go/no-go table, rollback rehearsals.",                     "status": "done"},
            {"id": 1,  "title": "Restore the pulse",     "purpose": "Scheduler repair, alerting revival, offsite backup.",                        "status": "done"},
            {"id": 2,  "title": "Make the books true",   "purpose": "Entries, COGS, FX, cash, stock, returns, ads, quarantine, residuals.",       "status": "active"},
            {"id": 3,  "title": "Turn truth into money", "purpose": "Floors, leak-stop, relists, liquidation tranche-1, storefront.",             "status": "pending"},
            {"id": 4,  "title": "Make it stay fixed",    "purpose": "PO governance, PPCH v1, telemetry, weekly digest, watchdog.",                "status": "pending"},
            {"id": 5,  "title": "Final inspection",      "purpose": "Score all 71 gates, owner acceptance.",                                      "status": "pending"},
        ],
        "gates": gates,
        # newest first; cap ~20. gate/lane events only — NO secrets, msg-ids, or PII.
        "activity": [
            {"ts": "2026-06-13T13:47+05", "text": "Handoff authored (Opus 4.8 1M); paused at Phase-1/2 boundary for fresh-chat switch"},
            {"ts": "2026-06-13T05:23+05", "text": "Phase 1 alerting GREEN — Telegram plumbed to 19 jobs; forced-failure proof received; offsite backup live (daily 05:30)"},
            {"ts": "2026-06-13T05:10+05", "text": "Phase 1 scheduler PARTIAL — interpreter fixed; 9 jobs parked on Phase-2 data (not infra)"},
            {"ts": "2026-06-13T04:45+05", "text": "Owner approved 3-day compression; AMD-11 LINE31 guard satisfied-by-structure"},
            {"ts": "2026-06-13T04:30+05", "text": "3-pass OCR reconciled — 166 additions + 12 supersede; LINE51 S=82"},
            {"ts": "2026-06-13T04:00+05", "text": "Phase -1 backup GREEN — 9.26 GB ×2 volumes; restore tests 3/3 PASS"},
            {"ts": "2026-06-13T03:00+05", "text": "Section-B data drops validated live (Telegram, cash col-M, counts, backups)"},
            {"ts": "2026-06-12T22:34+05", "text": "Owner decision session — 30 decisions + 11 amendments recorded"},
            {"ts": "2026-06-12T20:00+05", "text": "Program pack delivered — 71-gate matrix, master plan, starter pack"},
        ],
    }

    js = (
        "// progress-data.js — SINGLE SOURCE the orchestrator edits (window.GP only).\n"
        "// The renderer (dashboard.html) derives EVERY number from this object;\n"
        "// never edit the HTML. Generated by build_seed.py at handoff; hand-edit\n"
        "// thereafter: flip a gate status, bump `updated`, push an activity line.\n"
        "// Fixed status vocabulary: GREEN ARMED PARTIAL RED PENDING WAIVED OFF.\n"
        "// NEVER put secrets, tokens, message contents, or customer PII in here.\n"
        "window.GP = " + json.dumps(gp, indent=2, ensure_ascii=False) + ";\n"
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(js)

    g = gates
    print(
        "wrote {} : {} gates | GREEN={} ARMED={} PARTIAL={} PENDING={} | HARD={} ADV={}".format(
            out, len(g),
            sum(1 for x in g if x["status"] == "GREEN"),
            sum(1 for x in g if x["status"] == "ARMED"),
            sum(1 for x in g if x["status"] == "PARTIAL"),
            sum(1 for x in g if x["status"] == "PENDING"),
            sum(1 for x in g if x["type"] == "HARD"),
            sum(1 for x in g if x["type"] == "ADV"),
        )
    )
    # per-phase sanity
    from collections import Counter
    ph = Counter(x["phase"] for x in g)
    print("per-phase:", dict(sorted(ph.items())))


if __name__ == "__main__":
    main()
