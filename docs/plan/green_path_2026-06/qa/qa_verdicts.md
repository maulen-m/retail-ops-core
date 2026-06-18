# QA verdicts (3 adversarial passes, all by non-author Opus agents)

## QA-1 — reconciliation completeness: PASS_WITH_FINDINGS → all 5 fixed
- Coverage verified: 17/17 INEF, 12/12 OD, 8/8 missed classes, 6/6 paper asks; §5.14/§5.15 INEF-swap trap checked; all arithmetic spot-checks exact; all 6 source-conflicts resolved with explicit winners.
- FIXED: missing 11th metric → EXT-M11 added (exception age × KZT exposure); narrative self-count corrected (86 dispositions: 17+12+35+10+6+6); CN-065 retagged AUDIT-VINTAGE; single-write-orchestrator made explicit (EXT-A02); roadmap 7-dimension scores retained in EXT-R01.

## QA-2 — D2/D4 cross-consistency: PASS_WITH_FINDINGS → all 10 fixed
- 40/40 verify_cmd scripts exist on disk; 0 dangling CN refs; YAML 30/30 complete with param slots.
- FIXED (4 HIGH): G-LIQ-02↔G-WA-01 circular dependency broken (G-WA-01 now depends on G-STOCK-03;G-PRICE-04); FX-DEFER incoherence resolved (G-PRICE-01 dual-path: v7 needs G-FX-02, v6-reaffirm needs nothing — fallback lanes actually proceed); dangling OD-012 repointed to OD-019; 3 malformed CSV rows quoted (G-COGS-03/G-CASH-02/G-STOCK-03 — the last had severed the INBOUND→count→snapshot machine-readable ordering).
- FIXED (4 MED + 2 LOW): census corrected to 71 gates / 61 HARD / 10 ADVISORY; LINE51 explicitly EXCLUDED from the OD-018 5M cap (its 5.10M position alone exceeds it); LINE31 day-0 action classified (reversible external, pre-authorized, not a write); G-STOCK-05 + G-PRICE-05 promoted to HARD; OD-028 consumer named; OD-032 wired into G-LIQ-02/03.

## QA-3 — no-owner-mid-flight simulation: PASS_WITH_FINDINGS → HIGH fixed
- **Core property holds: 15 owner-contact hits, ALL legitimate (YAML refs / STOP-THE-LINE / acceptance / session-itself); 0 illegitimate.** All 21 packets' failure branches terminate in policy | park | stop-the-line. Write-before-backup: clean (LINE31 exception consistent in all 5 mentions). Single-writer: consistent, no overlapping write scopes. Secrets: zero values anywhere. YAML key paths: 18/18 exact. Acceptance: complete incl. wave-2 lists.
- FIXED (HIGH): orphan HARD gate G-LINE31-01 had no executing packet → PKT-STOREFRONT extended (daily spend-vs-stock cross-check job, depends G-STOCK-03) + plan §3 aligned. Gate⇄packet bijection now 71/71.
- ACCEPTED-BY-DESIGN (LOW): Section-B data drift (bank account missing, Telegram credential dead despite in-session pass) → STOP-THE-LINE is the intended single escape hatch; mitigated by the in-session validation requirement.
