# WILDBERRIES EXPANSION STRATEGY

**CSI Region Sports Apparel Business**

Strategic Analysis & Execution Plan

**Version:** 5.0  
**Updated:** December 2025  
**Parameter Reference:** `Master_Inventory_Rules_v6.md` §3.2

---

## EXECUTIVE SUMMARY

### Business Overview

You operate a 25M KZT e-commerce business selling sports apparel (Line51 and Line52 product lines) across Kazakhstan via Kaspi marketplace. Current operations generate approximately 3M KZT monthly profit with a blended portfolio ROIC of 16-21% monthly. The strategic objective is expansion into Russia's 140M+ consumer market through Wildberries marketplace.

### The Core Opportunity

Analysis of 12 scenarios across both product lines and platforms reveals that WB Line52 at 2,800₽ SPP delivers the optimal entry point with 68.2% monthly ROIC—nearly double your current Kaspi performance. With 5M KZT test capital (20% of total), downside is capped at ~1M KZT while upside potential is 3-4M KZT additional monthly profit.

### Key Metrics Summary

| Metric           | Current (Kaspi) | Target (WB)        |
|------------------|-----------------|--------------------|
| Total Capital    | 25M KZT         | 25M KZT            |
| Monthly Profit   | 2.94M KZT       | 5.5-6.5M KZT       |
| Portfolio ROIC   | 16.3%/month     | 24-28%/month       |
| Market Coverage  | Kazakhstan only | KZ + Russia        |

---

## SECTION 1: PROJECT ACHIEVEMENTS TO DATE

### 1.1 Comprehensive Financial Modeling Completed

We have built a robust analytical framework covering unit economics, inventory management, and capital allocation across both platforms and product lines.

**Unit Economics Analysis**

| Parameter | Value | Source |
|-----------|-------|--------|
| COGS Line51 | 6,019 KZT/unit | Master Rules §6.3 |
| COGS Line52 | 5,005 KZT/unit | Master Rules §6.3 |
| WB_commission | 24.5% | WB-specific (Master Rules §3.2) |
| WB_logistics_storage | 408₽/unit avg | WB-specific |
| WB_return_rate | 25% | WB-specific (vs Kaspi ~5%) |
| VAT_rate | 3% | Master Rules §4.1 (inherited) |
| FX_RUB_KZT | 6.6 | Master Rules §2 (inherited) |
| FX_USD_KZT | 530 | Master Rules §2 (inherited) |
| FX_CNY_KZT | 78 | Master Rules §2 (inherited) |

> **Note:** FX rates and VAT are Master-owned. WB inherits these values. See `Master_Inventory_Rules_v6.md` §3.0 for inheritance rules.

**Price-Demand Relationship Established**

Using real competitor data from WB marketplace (mpstats.io plugin) and your historical sales data, we've established demand curves:

| Product | Price (SPP) | Expected D/day | Data Source     |
|---------|-------------|----------------|-----------------|
| Line51  | 2,460₽      | 26             | Competitor data |
| Line51  | 3,044₽      | 10             | Competitor data |
| Line52 | 2,776₽      | 20             | RoomSport comp. |
| Line52 | 2,071₽      | 117            | Sahariev comp.  |

### 1.2 Inventory Management Framework

Implemented King's formula with safety stock calculations optimized for WB's unique payment cycle and multi-warehouse distribution model.

**Lead Time Parameters**

| Param | Value | Source | Notes |
|-------|-------|--------|-------|
| `L1` | 21 days | Master Rules §4.1 | China → Astana (inherited) |
| `L2` | 1 day/200 units | WB-specific | Fulfillment prep |
| `L3` | 10 days | WB-specific | Astana → WB warehouses |
| `L_total` | **~32 days** | `= L1 + L2 + L3` | WB total lead time |

**Safety Stock Parameters**

| Param | Value | Source |
|-------|-------|--------|
| `B` (Buffer) | 14 days | Master Rules §4.1 (inherited) |
| `R` (Review) | 10 days | Master Rules §4.1 (inherited) |
| `z` (Service) | 1.65 | Master Rules §4.1 (inherited) |
| `TV` (Mix var) | 0.23 | Master Rules §4.1 (inherited) |
| `σ_factor` | 0.4 | Master Rules §4.1 (inherited) |

**WB-Specific Cash Cycle**

| Param | Value | Notes |
|-------|-------|-------|
| `WB_payment_cycle` | 7-day sales + 11-day delay | vs Kaspi 2-day payout |
| `WB_warehouse_split` | Multi-region | Moscow, Kazan, Novosibirsk, etc. |

> **Inheritance Note:** All params not listed as "WB-specific" inherit from Master Rules §4.1. See `Master_Inventory_Rules_v6.md` §3.0 for the full inheritance model.

### 1.3 Scenario Comparison Matrix

12 scenarios analyzed across price points, products, and platforms. Top 3 scenarios identified:

| Rank | Scenario      | Price   | Monthly | K_avg | ROIC/month |
|------|---------------|---------|---------|-------|------------|
| #1   | WB Line52    | 2,800₽  | 2.95M   | 4.33M | 68.2%     |
| #2   | WB Line51     | 3,000₽  | 2.62M   | 5.02M | 52.2%     |
| #3   | Kaspi Line51  | 15,990₸ | 1.10M   | 2.81M | 50%       |

---

## SECTION 2: STRATEGIC GOALS & PURPOSE

### 2.1 Primary Objective: Market Expansion

The business is not about replacing Kaspi—it's about capturing an entirely new demand pool. Kazakhstan (5M addressable consumers) vs Russia (140M+ addressable consumers). This is a 28x market size expansion opportunity.

**Why Wildberries Specifically**

- Largest marketplace in Russia (52% market share in fashion)
- Your product category (sport apparel) performs well—competitor data shows D=10-26/day achievable
- Multi-warehouse distribution maximizes regional reach
- Established KZ seller pathway (ТОО ИМВВКЗ entity)

### 2.2 Secondary Objectives

**Platform Risk Diversification**

Currently 100% revenue from Kaspi = single point of failure. Adding WB creates revenue resilience against platform-specific risks (policy changes, commission increases, algorithm shifts).

**Currency Hedge**

RUB/KZT at 6.6 is historically favorable. Revenue in RUB diversifies against KZT-only exposure. WB payments convert to KZT upon bank receipt, locking in favorable rates.

**Growth Ceiling Breakthrough**

Kaspi Line51 is at ~80% market capacity (D=8 ceiling). Kaspi Line52 has 7 competitors creating price war pressure. WB offers uncapped demand potential in a 28x larger market.

### 2.3 Ultimate Vision: CSI Region Dominance

The long-term play is establishing dominant market position in sport apparel across the Commonwealth of Independent States. This requires:

- Proven unit economics on WB (current focus)
- Brand registry completion on Kaspi (6 months)
- Scale to 200-300K USD capital base
- Multi-SKU portfolio expansion
- Potential Ozon/Lamoda expansion

---

## SECTION 3: WEAKEST LINKS & ROOT CAUSES

### 3.1 Operational Weaknesses

**Weakness #1: Accounting & Data Infrastructure**

**Severity:** HIGH

You stated: "I'm still trying to standardize my accounting workflow via Excel and vibe-coding autonomous CRM system. So I'm not super sure about any numbers."

**Root Cause:** Manual, fragmented data entry across multiple systems without automated reconciliation.

**Impact:** Cannot accurately track K_avg, true ROIC, or make data-driven scaling decisions. Flying blind on actual performance.

**Solution:** Implement daily KPI tracking dashboard with automated data feeds from Kaspi seller portal, WB seller portal, and bank statements. Priority: Build before scaling WB.

**Weakness #2: Lead Time Variability**

**Severity:** MEDIUM

L1 (China→Astana) ranges from 15-60 days. Two instances of 60+ day delays in 4 years due to customs freezes.

**Root Cause:** Customs clearance unpredictability at Kazakhstan border.

**Impact:** Safety stock must buffer for worst case, increasing capital requirements by ~40%.

**Solution:** Maintain 14-day safety buffer (B=14, per Master Rules §4.1). Consider customs broker relationship for priority handling. At 200K+ USD capital, evaluate direct China→Moscow air freight.

**Weakness #3: No Brand Protection**

**Severity:** HIGH

Brand registry pending (6 months). Until completion, competitors can sell under your listings on Kaspi.

**Root Cause:** Trademark registration process timeline in Kazakhstan.

**Impact:** Line52 revenue shared with 7 other sellers. Cannot defend pricing power. Vulnerable to copycats.

**Solution:** Complete brand registry process. After completion: guaranteed 70%+ of current Kaspi sales protected. Do not aggressively scale Kaspi Line52 until registry completes.

### 3.2 Strategic Weaknesses

**Weakness #4: Single Market Concentration**

**Severity:** MEDIUM

100% revenue from Kazakhstan market through Kaspi platform.

**Root Cause:** Historical focus on proven market before expansion.

**Impact:** Platform policy changes, commission increases, or market saturation directly threatens entire business.

**Solution:** WB expansion addresses this directly. 5M KZT test capital (20% of total) aligns with `max_new_SKU_capital_pct` rule (Master Rules §4.3).

**Weakness #5: Demand Estimation Uncertainty**

**Severity:** MEDIUM

Historical WB data is 2 years old. Your own Line51 WB test data (Sept-Dec 2024) shows only 11 days of meaningful sales in "Костюмы" category before stock depletion.

**Root Cause:** Market conditions evolve. Limited recent data points.

**Impact:** Demand projections carry 20-30% uncertainty. Conservative estimates essential.

**Solution:** Apply `new_SKU_0d_factor = 0.50` from Master Rules §4.5 for initial orders. Price testing ladder with defined triggers. Start conservative (3,000₽), lower only if demand disappoints.

---

## SECTION 4: COMPREHENSIVE EXPANSION STRATEGY

### 4.1 Phase 1: Market Validation (Months 1-2)

Objective: Prove WB unit economics with minimal capital exposure.

**Capital Allocation**

| Component                      | Amount      | % of Total |
|--------------------------------|-------------|------------|
| Line52 Inventory (425 units)  | 2.25M KZT   | 45%        |
| China→Astana Cargo             | 0.57M KZT   | 11%        |
| Astana→WB Delivery             | 0.12M KZT   | 2%         |
| WB Ads (2 months @ 275K)       | 0.55M KZT   | 11%        |
| Working Capital Buffer         | 1.51M KZT   | 30%        |
| **TOTAL WB TEST CAPITAL**      | **5.0M KZT** | **20%**   |

> **Note:** 20% allocation complies with `max_new_SKU_capital_pct` rule (Master Rules §4.3).

**Product Selection Rationale**

Lead with Line52, not Line51. Line52 has 21% lower COGS (5,005 vs 6,019 KZT per Master Rules §6.3), better competitor price data, and historical WB demand curves. This reduces validation risk while maintaining high ROIC potential (68.2% at optimal price).

**Product Scope**

| Product_Type | WB Status | Reference |
|--------------|-----------|-----------|
| CL (Clothes) | **Active** | Master Rules §3.2 |
| ELS (Electronics) | Not on WB | Master Rules §1.1 — Kaspi only |

**Pricing Strategy**

Starting Price: 2,800₽ SPP (3,500₽ listed)

This positions slightly above RoomSport competitor (2,776₽) to signal quality while remaining competitive. Conservative D=12/day target.

Price Testing Ladder:

- Start: 2,800₽ (D=12 target) — Monitor for 2 weeks
- If D<8: Lower to 2,500₽ (D=18 target)
- If D<14 at 2,500₽: Lower to 2,200₽ (D=30 target) — Still 39.4% monthly ROIC!
- If D<20 at 2,200₽: EXIT — Liquidate on Kaspi at 8,000 KZT

**Success Metrics**

| Metric | Target | Gate |
|--------|--------|------|
| Daily sales velocity | ≥10 units/day | Within 30 days |
| Return rate | ≤30% | WB_return_rate = 25% baseline |
| Monthly ROIC | ≥40% | Above ROIC_auto_approve (20%) |
| Unit economics | Positive | At actual demand |

> **ROIC Gate Reference:** Master Rules §4.2 defines ROIC_auto_approve = 20%. WB target of 40%+ is 2x the auto-approve threshold.

### 4.2 Phase 2: Optimization (Months 3-4)

Objective: Maximize ROIC through price point optimization and ad efficiency.

**Actions**

- Analyze first 60 days of data: actual D, return rates, ad conversion
- Optimize price point based on demand elasticity observed
- Scale ads from 100K→275K/month if unit economics positive
- Add Line51 to WB if Line52 validates successfully

**Line51 WB Entry (Conditional)**

If Line52 achieves ≥40% ROIC, deploy additional 2M KZT for Line51 test at 3,000₽ SPP. Different product category ("Костюмы") may capture different customer segment.

**New SKU Factor Application**

| Scenario | Days History | Factor | Source |
|----------|--------------|--------|--------|
| Line52 initial | 0 | 0.50 | Master Rules §4.5.1 |
| Line52 @ 30d | 30 | 0.75 | Master Rules §4.5.1 |
| Line51 if added | 0 | 0.50 | Master Rules §4.5.1 |

### 4.3 Phase 3: Scale (Months 5-12)

Objective: Aggressive capital deployment to proven SKUs.

**Scale Triggers**

- Brand registry completes on Kaspi (Month 6)
- WB ROIC confirmed ≥40% for 90+ days (above `new_SKU_90d_factor` threshold)
- Total capital reaches 15M+ KZT available for WB

**Scale Actions**

- Increase WB capital allocation to 40-50% of total (10-12M KZT)
- Add New-CLO product lines to WB
- Expand warehouse distribution for regional coverage
- Consider Ozon as third platform

---

## SECTION 5: RISK MANAGEMENT FRAMEWORK

### 5.1 Capital Exposure Limits

**Golden Rule:** Never deploy more than 20% of total capital to unproven opportunities.

| Allocation | Amount | % | Rule Reference |
|------------|--------|---|----------------|
| WB test cap | 5M KZT | 20% | Master Rules §4.3 |
| Kaspi base protected | 18-20M KZT | 80% | — |
| **Total** | 25M KZT | 100% | — |

### 5.2 Exit Triggers

| Trigger Condition                     | Action                      | Timeline |
|---------------------------------------|-----------------------------|----------|
| D<8 at 2,800₽ for 14 days             | Lower price to 2,500₽       | Week 2   |
| D<14 at 2,500₽ for 14 days            | Lower price to 2,200₽       | Week 4   |
| D<20 at 2,200₽ for 14 days            | EXIT: Liquidate on Kaspi    | Week 6   |
| Return rate >40% sustained            | Review product quality      | Any time |
| ROIC < 10% for 30 days                | REVIEW_REQUIRED per §4.2    | Any time |

> **ROIC Gate:** If WB ROIC falls below `ROIC_flag_threshold` (10%), triggers human review per Master Rules §4.2.

### 5.3 Downside Scenario Analysis

**Worst Case:** WB completely fails. D<5 at all price points.

- Action: Liquidate inventory on Kaspi at 8,000 KZT (Line52) or 12,990 KZT (Line51)
- Recovery: ~4M of 5M deployed (only logistics loss)
- Maximum loss: ~1M KZT (4% of total capital)

**Base Case:** WB achieves conservative estimates.

- D=12 at 2,800₽ SPP
- Monthly profit: 2.5-3.0M KZT additional
- Combined portfolio: 5.5-6.5M KZT/month

**Upside Case:** WB matches competitor performance.

- D=20+ at 2,800₽ SPP
- Monthly profit: 4-5M KZT additional
- Combined portfolio: 7-8M KZT/month

---

## SECTION 6: COMPETITIVE ADVANTAGES & MOATS

### 6.1 Current Advantages

**Cost Structure**

| Improvement | Old | New | Savings |
|-------------|-----|-----|---------|
| Line52 supplier | 64 CNY | 47 CNY | 27% |
| Cargo rate | 3.4 $/kg | 2.66 $/kg | 22% |
| Combined | — | — | ~1,400 KZT/unit |

> **Reference:** Current cargo rate per Master Rules §2.1.

**Operational Knowledge**

- Established China supplier relationships (time-tested, incentivized long-term)
- Astana fulfillment infrastructure in place
- Multi-warehouse WB distribution strategy mapped

**Market Position**

- Only Line51 seller on Kaspi (monopoly position)
- Line52: Better unit economics than 7 competitors on Kaspi
- WB: Category change to "Костюмы" showed strong initial traction

### 6.2 Moats Under Construction

**Brand Registry (6 months)**

Once completed: 70%+ of current Kaspi sales protected. Competitors cannot sell under your listings. Price war pressure eliminated.

**Multi-Platform Presence**

Operating across Kaspi + WB creates operational complexity barrier for competitors. Cross-platform insights enable better demand forecasting.

**Inventory Management Excellence**

You stated: "Our main competitive advantage will be most efficient logistics, and autonomous, highly efficient inventory management via coding/math and AI tools." This analytical approach—King's formula, safety stock optimization, multi-warehouse distribution—creates sustainable operational advantage.

> **System Reference:** Project 3 (CRM Build) implements Master Rules formulas in Python/DB. See `Master_Inventory_Rules_v6.md` for formula definitions.

---

## SECTION 7: IMMEDIATE ACTION ITEMS

**This Week (Days 1-7)**

| Day  | Action                                              | Owner |
|------|-----------------------------------------------------|-------|
| 1    | Confirm supplier can deliver 425 Line52 units      | Adil  |
| 1-2  | Set up WB seller account (if not active)            | Adil  |
| 2    | Create Line52 product cards on WB portal           | Adil  |
| 3    | Place PO with supplier, confirm delivery timeline   | Adil  |
| 5-7  | Set up daily KPI tracking spreadsheet               | Adil  |

**Next 30 Days**

- Day 1-3: Place PO with supplier for 425 Line52 units
- Day 21-25: Receive shipment in Astana (L1 = 21 days per Master Rules)
- Day 26: Package according to WB requirements
- Day 27-35: Ship to WB warehouses (L3 = 10 days)
- Day 36+: Begin sales, start daily KPI tracking

**Daily KPI Tracking Template**

| KPI                  | Target | Warning | Exit    |
|----------------------|--------|---------|---------|
| Daily Sales (D)      | ≥12    | 8-11    | <8      |
| Return Rate          | ≤25%   | 26-35%  | >40%    |
| Ad Conversion Cost   | <500₽  | 500-750₽ | >1000₽ |
| Stock Days Remaining | >21    | 14-20   | <14     |

---

## SECTION 8: PARAMETER REFERENCE SUMMARY

### WB Channel Parameters (from Master Rules §3.2)

**Inherited from Master (do not duplicate):**
- L1, R, B, z, TV, σ_factor — see Master Rules §4.1
- FX rates (CNY, USD, RUB) — see Master Rules §2
- VAT_rate — see Master Rules §4.1
- ROIC gates — see Master Rules §4.2
- Size mix guardrails — see Master Rules §4.4 (CL only)
- New SKU factors — see Master Rules §4.5

**WB-Specific (defined here):**

| Param | Value | Notes |
|-------|-------|-------|
| `L2` | 1 day/200 units | Fulfillment prep |
| `L3` | 10 days | Astana → WB warehouses |
| `L_total` | ~32 days | `= L1 + L2 + L3` |
| `WB_commission` | 24.5% | vs Kaspi 12.5% |
| `WB_logistics_storage` | 408₽/unit | Combined fee |
| `WB_return_rate` | 25% | vs Kaspi ~5% |
| `WB_payment_cycle` | 7d sales + 11d delay | Complex payout |

**Unit Economics Formula (WB):**

```
Net_rev_unit = (SPP_RUB × (1 - 0.245) - 408) × 6.6 × (1 - 0.03)
COGS_unit    = BaseCost_CNY × 78 + Weight_kg × 2.66 × 530
Unit_Profit  = Net_rev_unit - COGS_unit
```

> **Reference:** Master Rules §6.2

---

## CONCLUSION

The Wildberries expansion represents a calculated growth opportunity, not a gamble. With 5M KZT test capital (20% of total), maximum downside is ~1M KZT (4% of capital) while upside potential is 3-5M KZT additional monthly profit.

Key success factors:

- Lead with Line52 (lower COGS, better data)
- Start at 2,800₽ SPP (conservative, high ROIC potential)
- Use price testing ladder with defined exit triggers
- Implement daily KPI tracking from day 1
- Protect Kaspi base (80% of capital) during validation
- Apply `new_SKU_0d_factor = 0.50` for initial orders (Master Rules §4.5)

The path to CSI region dominance in sport apparel runs through this WB test. Execute disciplined, measure rigorously, scale aggressively once validated.

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 4.0 | 2025-11 | Initial strategic document |
| **5.0** | **2025-12** | **Refactored to reference Master_Inventory_Rules_v6.md.** Removed duplicated parameters. Added inheritance notes. Added §8 parameter reference summary. |

---

*This document references `Master_Inventory_Rules_v6.md` as the single source of truth for shared parameters. Do not duplicate values here—inherit or explicitly override.*
