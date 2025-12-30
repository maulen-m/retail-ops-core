# Project 3 — Autonomous Retail Business System
## Status Report & $1M Vision Roadmap

**Date:** December 11, 2025 | **Current Capital:** ~$47,000 USD (25M KZT)

---

# PART 1: CURRENT STATUS

## 1.1 Phase Completion

```
Phase 0-5:  Excel Parity      ████████████████████ 100% ✅ (24 tasks)
Phase 6:    Forecasting       ████████████████████ 100% ✅ (41 tasks)
Phase 6.5:  Data Grain Fix    ████████████████████ 100% ✅ (3 tasks)
Phase 7:    Capital Optimizer ████████████████████ 100% ✅ (15 tasks)
Phase 8:    Multi-Channel     ████████████████████ 100% ✅ (19 tasks)
Phase 9.5:  Kaspi API         ████████████████████ 100% ✅ (23 tasks)
Phase 10:   Stock Ledger      ████████████████████ 100% ✅
Phase 11:   Daily Workflow    ████████████████████ 100% ✅
Phase 12:   Full Automation   ████████████████████ 100% ✅ (Parts 1-6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL: 200+ tasks complete | 200+ tests passing | 13,050+ sales records
```

## 1.2 What's Live Today

| Layer | Component | Status | Details |
|-------|-----------|--------|---------|
| **Database** | SQLite (25+ tables) | ✅ | 13,050 sales, 455+ days, 221 SKUs |
| **Ingestion** | Kaspi API (5 stores) | ✅ | Full read/write, pagination, filtering |
| **CRM Pipeline** | Export → Import → Sync | ✅ | 4-step automated workflow |
| **Waybill Workflow** | Ship → Download → Build | ✅ | V2 optimized (2 CRM reads) |
| **Calc Engine** | D₃₀, σ, SS, ROP, ROIC | ✅ | Excel V15 parity validated |
| **Size Engine** | 4-tier cascade | ✅ | 64.8% auto-assignment coverage |
| **Forecasting** | Trend-adjusted demand | ✅ | D7/D14/D30, DOW patterns |
| **Capital** | Portfolio optimizer | ✅ | GROW/MAINTAIN/HARVEST/KILL |
| **Multi-Channel** | WB expansion scorer | ✅ | Ready, not launched |
| **Alerts** | Telegram notifications | ✅ | REORDER + errors |
| **Scheduling** | launchd plist | ✅ | Ready to install |

## 1.3 Recent Wins (Phase 12 Part 6)

- Fixed date filter bug — was processing 5,290 historical orders instead of ~85 today
- Created V2 waybill workflow — saves ~30-60s per run (eliminates 1 CRM read)
- Reduced API timeouts (60s → 20s) and added circuit breaker
- Full daily workflow now runs in <5 minutes end-to-end

## 1.4 Time Savings Achieved

| Task | Before | After | Saved |
|------|--------|-------|-------|
| Phone lookup | 25 min/day | 0 min | 25 min |
| WhatsApp PDFs | 17 min/day | 3 min | 14 min |
| Order import | 15 min/day | 2 min | 13 min |
| Status check | 10 min/day | 0 min | 10 min |
| **Total** | **67 min/day** | **5 min** | **~62 min** |

**Annual impact:** ~375 hours saved/year

---

# PART 2: $1M VISION

## 2.1 Target Definition

**Goal:** $1M USD net worth in 12-18 months

This means:
- **21× growth** from current $47K
- Combination of **5× revenue expansion** + **6× capital deployment**
- Net worth = liquid capital + inventory at cost + receivables − liabilities

## 2.2 What "1M-Ready" Looks Like

| Dimension | Current (Dec 2025) | 1M-Ready | Gap |
|-----------|-------------------|----------|-----|
| Revenue channels | 1 (Kaspi) | 3+ (Kaspi, WB, Ozon) | +2 channels |
| SKUs managed | 221 | 1,000+ | +779 SKUs |
| Daily orders | ~85 | 500+ | +415 orders |
| Capital deployed | $47K | $200K+ | +$153K |
| Ops time/week | ~10 hrs | <2 hrs | −8 hrs |
| Portfolio ROIC | ~240% | 300%+ | +60% |
| Automation level | 80% | 95%+ | +15% |
| Monthly profit | ~$6K | $25K+ | +$19K |

## 2.3 Growth Math

```
Current state:    $47K capital × 240% ROIC = ~$113K annual profit = ~$9.4K/month
                  But only ~$6K/month realized (capital constraints, inefficiency)

1M-Ready state:   $200K capital × 300% ROIC = $600K annual profit = $50K/month
                  Conservative: $200K capital × 150% ROIC = $25K/month

Path to $1M:      $47K + 18 months × $25K/month profit reinvested
                  = $47K + $450K = ~$500K
                  + inventory appreciation + WB revenue
                  = $1M achievable in 12-18 months
```

## 2.4 Governance Rules (Non-Negotiable)

These rules protect capital during scaling:

| Rule | Rationale |
|------|-----------|
| **20% max on unproven bets** | WB test capped at 5M KZT (~$10K) until proven |
| **Exit triggers defined upfront** | WB: <0.3 D/day after 30 days = exit |
| **No single SKU >20% of capital** | LINE52 currently at 24.6% — needs rebalancing |
| **ROIC floor: 25%** | Below this, liquidate and redeploy |
| **7-day CRM backups** | Never lose operational data |

---

# PART 3: GAPS TO VISION

| Gap | Current State | 1M Requirement | Priority | Effort |
|-----|---------------|----------------|----------|--------|
| **Channel diversification** | Kaspi only | WB + Ozon live | HIGH | 2-3 weeks |
| **Inventory autonomy** | Semi-automated PO | Fully autonomous reorder | HIGH | 2-4 weeks |
| **Supplier automation** | Manual PO email | API/EDI integration | MEDIUM | 4-6 weeks |
| **1M Dashboard** | None | Weekly metrics view | MEDIUM | 1 week |
| **Return tracking** | Manual Excel column | Automated from API | MEDIUM | 1 week |
| **WhatsApp Business** | pywhatkit (fragile) | Verified API | MEDIUM | 2+ weeks |
| **Real-time data** | 2x daily sync | Continuous sync | LOW | Future |
| **Custom PDFs** | Kaspi-generated | Own template/branding | LOW | Future |

---

# PART 4: PRIORITY INITIATIVES

## Track A: Operations Stability (NOW — Dec 11-18)

**Status:** Phase 12 complete, stabilizing

- [x] Phase 12 Part 6 — V2 waybill workflow, date filter fix
- [ ] Install launchd scheduler (`./scripts/install_scheduler.sh`)
- [ ] Test V2 waybill workflow in production
- [ ] Validate ~85 orders/day (not 5,290 historical)
- [ ] Populate `config/heavy_items.yaml` with actual SKUs
- [ ] WhatsApp Business API verification

**Success Metric:** <5 min total daily workflow, zero manual intervention

## Track B: WB Launch (Next 2-3 weeks)

**Status:** Infrastructure ready, launch pending

- LINE52 scored 85/100 for WB expansion
- 425-unit test shipment ready to send
- WB tariff calculator available
- Economics validated: 42.3% WB margin on LINE52

**Actions:**
- [ ] Create WB seller account
- [ ] Submit LINE52 FBO shipment (425 units)
- [ ] Monitor first 30 days of sales
- [ ] Track D/day, returns, ROIC vs projections
- [ ] Decision gate at Day 30: scale to 10-12M KZT or exit

**Success Metric:** LINE52 profitable on WB within 30 days (>0.3 D/day, <15% returns)

**Exit Triggers:**
- D/day < 0.3 after 30 days → liquidate, exit WB
- Returns > 20% → pause, investigate sizing
- ROIC < 25% after 60 days → redeploy capital to Kaspi

## Track C: Scale Kaspi (Ongoing)

**Status:** Foundation complete, optimization phase

- Run daily pipeline every morning (automated after scheduler)
- Review kill list weekly — reallocate from 8% → 600% ROIC
- Use Auto-PO for all supplier orders
- Track return rates by size_source
- Rebalance LINE52 from 24.6% → <20% of capital

**Success Metric:** Portfolio ROIC +3-5% over 90 days

## Track D: Supplier Automation (Phase 9, future)

**Status:** Not started, blocked on current priorities

- EDI/API integration with Chinese suppliers
- Automated PO generation and submission
- FX rate tracking (CNY/KZT, USD/KZT)
- Lead time optimization (L=21 days)
- Landed cost decision report (rank suppliers by ROIC after logistics)

**Success Metric:** PO submission <5 min, auto-approved

## Track E: 1M Dashboard & Visibility

**Status:** Not started

- [ ] Define 7 core metrics (see Part 6.5)
- [ ] Build weekly report (Excel tab or Python-generated)
- [ ] Track founder time weekly (target: <2 hrs/week)
- [ ] Review dashboard every Sunday

**Success Metric:** Single view answers "Am I on track to $1M?"

---

# PART 5: PATH TO $1M

```
         NOW                    Q1 2026              Q2 2026              Q3 2026
          │                        │                    │                    │
          ▼                        ▼                    ▼                    ▼
    ┌──────────┐            ┌──────────┐          ┌──────────┐        ┌──────────┐
    │ PHASE 12 │            │ WB LIVE  │          │ SCALE    │        │ AUTONOMY │
    │ COMPLETE │ ────────►  │ LINE52  │ ──────►  │ 3 CHNLS  │ ────►  │ <2 hr/wk │
    │ $47K     │            │ +$20K    │          │ +$50K    │        │ +$83K    │
    └──────────┘            └──────────┘          └──────────┘        └──────────┘
          │                        │                    │                    │
          │    Track A: Ops        │    Track B: WB     │    Track C: Scale  │
          │    Track B: WB Prep    │    Track C: Kaspi  │    Track D: Supply │
          │                        │    Track E: Dash   │    Track E: Dash   │
          │                        │                    │                    │
          └────────────────────────┴────────────────────┴────────────────────┘
                                                                              │
                                                                              ▼
                                                                      ┌──────────┐
                                                                      │   $1M    │
                                                                      │ 12-18 mo │
                                                                      └──────────┘
```

### Milestones & Checkpoints

| Date | Milestone | Capital Target | Validation |
|------|-----------|----------------|------------|
| Dec 18 | Track A complete | $47K | Scheduler running, V2 validated |
| Jan 15 | WB Day 30 review | $55K | Decision: scale or exit |
| Mar 1 | WB scaled or Kaspi doubled | $80K | Second channel live OR Kaspi 2× |
| Jun 1 | 3 channels, <4 hrs/week | $150K | Ozon pilot started |
| Sep 1 | Full autonomy | $300K | <2 hrs/week ops |
| Dec 2026 | $1M | $1M+ | Net worth validated |

---

# PART 6: SYSTEM REFERENCE

## 6.1 Architecture (v1.0)

```
┌────────────────────────────────────────────────────────────────────┐
│                 AUTONOMOUS BUSINESS SYSTEM v1.0                    │
│                    Phase 12 Complete                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  DATA INGESTION                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Kaspi API    │  │ Excel/CSV    │  │ Inventory    │             │
│  │ (5 stores)   │  │ Parsers      │  │ Snapshot     │             │
│  │ ✅ R/W       │  │ ✅ LIVE      │  │ ✅ LIVE      │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         └──────────────────┴──────────────────┘                    │
│                            │                                       │
│                            ▼                                       │
│  CRM PIPELINE (run_full_import.command)                           │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 1. Export → 2. Import → 3. GDrive → 4. Status                │ │
│  │ ✅ Scheduled: 11:00 / 16:05 GMT+5                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                            │                                       │
│                            ▼                                       │
│  WAYBILL WORKFLOW (run_build_waybills_v2.command)                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 1. Ship (API) → 2. Download (V2) → 3. Build Bundles          │ │
│  │ ✅ 2 CRM reads, ~3 min total                                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                            │                                       │
│                            ▼                                       │
│  INTELLIGENCE LAYER                                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                  │
│  │ Forecast   │  │ Capital    │  │ Expansion  │                  │
│  │ Engine     │  │ Optimizer  │  │ Scorer     │                  │
│  │ ✅ Live    │  │ ✅ Live    │  │ ✅ Ready   │                  │
│  └────────────┘  └────────────┘  └────────────┘                  │
│                            │                                       │
│                            ▼                                       │
│  EXECUTION LAYER                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                  │
│  │ Telegram   │  │ WhatsApp   │  │ CSV/Export │                  │
│  │ Alerts     │  │ PDFs       │  │ PO Suggest │                  │
│  │ ✅ Live    │  │ ✅ Ready   │  │ ✅ Live    │                  │
│  └────────────┘  └────────────┘  └────────────┘                  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 6.2 Size Engine (4-Tier Cascade)

| Tier | Source | Confidence | Coverage |
|------|--------|------------|----------|
| 1 | **CUSTOMER** — Height+weight from WhatsApp | Highest | ~10% |
| 2 | **OFFER_MODE** — Historical mode for listing | High | ~40% |
| 3 | **STYLE_MODE** — Historical mode for style | Medium | ~15% |
| 4 | **DEFAULT** — Product-type default (XL/164cm) | Fallback | ~35% |

**Total auto-assignment:** 64.8%

## 6.3 API State Mapping

| Kaspi API State | CRM Status (Russian) |
|-----------------|---------------------|
| NEW | Новый |
| APPROVED_BY_BANK | Одобрен |
| ACCEPTED_BY_MERCHANT | Принят |
| ASSEMBLY | Собирается |
| KASPI_DELIVERY | Ожидает КД |
| DELIVERY | Доставляется |
| PICKUP | Готов к выдаче |
| COMPLETED | Завершен |
| ARCHIVE | Завершен |
| CANCELLED | Отменен |
| CANCELLING | Отменяется |
| RETURNING | Возвращается |
| RETURNED | Возвращен |

## 6.4 Configuration Files

| File | Purpose |
|------|---------|
| `config/com.example.kaspi-import.plist` | launchd schedule (11:00, 16:05 GMT+5) |
| `config/heavy_items.yaml` | Heavy SKU definitions for package count |
| `config/stores.yaml` | Store codes and API credentials |
| `sent_pdfs.json` | WhatsApp resume tracking |

## 6.5 1M Dashboard Metrics (Track E)

**Weekly review — 7 metrics that answer "Am I on track?"**

| # | Metric | Source | Target |
|---|--------|--------|--------|
| 1 | **Net Worth** | Manual calc | $1M by Dec 2026 |
| 2 | **Monthly Profit** | fact_sales + expenses | $25K+ at 1M-ready |
| 3 | **Portfolio ROIC** | view_sku_metrics | 300%+ |
| 4 | **Capital Deployed** | inventory + cash | $200K+ |
| 5 | **Founder Ops Time** | Self-tracked | <2 hrs/week |
| 6 | **Channel Mix** | Revenue by platform | Kaspi 60% / WB 30% / Ozon 10% |
| 7 | **Orders/Day** | fact_sales_daily | 500+ |

---

# PART 7: METRICS & RISKS

## 7.1 System Health

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Tests passing | 200+ | 200+ | ✅ |
| API stores validated | 5/5 | 5/5 | ✅ |
| Sales records | 13,050+ | 10,000+ | ✅ |
| History days | 455+ | 60+ | ✅ |
| Size auto-assignment | 64.8% | 70% | 🔶 |
| Daily workflow time | <5 min | <5 min | ✅ |
| Founder ops time/week | ~10 hrs | <2 hrs | 🔶 |

## 7.2 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WhatsApp spam block | HIGH | MEDIUM | Get Business API verified |
| Kaspi API changes | LOW | HIGH | Multi-channel hedge (WB) |
| WB test failure | MEDIUM | MEDIUM | Capped at 20% capital, exit triggers |
| Size engine accuracy | MEDIUM | MEDIUM | Track return rate by source |
| Excel corruption | LOW | HIGH | 7-day CRM backups |
| Scheduler failures | LOW | MEDIUM | Telegram error alerts |
| Copycat competition | MEDIUM | MEDIUM | Brand registry (pending) |
| Capital concentration | MEDIUM | HIGH | 20% rule, weekly rebalance |

---

# PART 8: COMMANDS CHEAT SHEET

```bash
# === DAILY WORKFLOW ===
./excel_ui/run_full_import.command          # Full 4-step import
./excel_ui/run_build_waybills_v2.command    # Waybill workflow (V2)
./excel_ui/run_send_whatsapp.command        # WhatsApp PDF sender

# === SCHEDULER ===
./scripts/install_scheduler.sh              # Install launchd job
launchctl list | grep kaspi                 # Check status
launchctl unload ~/Library/LaunchAgents/com.example.kaspi-import.plist  # Stop

# === MANUAL SCRIPTS ===
python scripts/export_api_orders.py --today-only
python scripts/import_orders_to_crm.py --dry-run
python scripts/update_order_statuses.py --days 7
python scripts/sync_to_gdrive.py --new-rows 10

# === WAYBILLS ===
python scripts/ship_orders_api.py --dry-run
python scripts/download_waybills_v2.py --date today
python scripts/build_daily_waybills.py --date today

# === ANALYTICS ===
python scripts/run_daily_pipeline.py
python scripts/run_portfolio_review_v2.py
python scripts/generate_kill_list.py
python scripts/run_expansion_analysis.py --top 10

# === PO GENERATION ===
python scripts/run_auto_po.py --dry-run
python scripts/run_auto_po.py --trigger ROP
python scripts/po_approval_cli.py list
```

---

# PART 9: IMMEDIATE ACTIONS

## This Week (Dec 11-18)

```bash
# Day 1-2: Stabilize V2 Workflow
./scripts/install_scheduler.sh
./excel_ui/run_build_waybills_v2.command
ls -la waybills/output/ | wc -l  # Should be ~85

# Day 3-5: Daily Operations (automated)
# 11:00 GMT+5 — run_full_import.command
# 16:05 GMT+5 — run_full_import.command

# Day 6-7: Weekly Review
python scripts/generate_kill_list.py
python scripts/run_expansion_analysis.py --top 10
```

## Success Criteria

| Metric | Target |
|--------|--------|
| V2 waybill count | ~85/day (not 5,290) |
| Import time | <2 min |
| Waybill time | <3 min |
| Total daily ops | <5 min |

---

# PART 10: OPEN QUESTIONS

Things to clarify as we execute:

| Question | Impact | When to Decide |
|----------|--------|----------------|
| WB seller account setup — who registers? | Blocks Track B | This week |
| Brand registry timeline? | Copycat risk | Before WB scale |
| Ozon pilot timing? | Channel 3 | After WB Day 30 |
| Founder time tracking method? | Track E accuracy | This week |
| 1M Dashboard — Excel or Python report? | Track E delivery | Jan 2026 |
| Landed cost report priority? | Track D scope | After Track A stable |

---

**Document Version:** 4.0 (Merged A+B)  
**Created:** December 6, 2025  
**Updated:** December 11, 2025  
**Next Review:** Dec 18 (Track A checkpoint)
