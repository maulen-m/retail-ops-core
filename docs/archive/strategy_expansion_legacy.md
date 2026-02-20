# Profit Growth Strategy: Weighted Risk/Return Portfolio Diversification for Kaspi Clothes Retail

## Context

AcmeWear operates on Kaspi marketplace selling men's compression sportswear (LINE52, LINE51, SUIT-61, T-SHIRT, KID-31, RUSH-PRO). Total capital ~22.4M KZT. Monthly profit ~4.6M KZT at ~41% margin. **Critical risk: 100% men/kids, zero women's products. LINE52_BLACK alone = 42% of daily clothing orders.** The business needs to diversify capital across new categories/genders to reduce concentration risk and capture untapped demand.

---

## Deliverable

Write a single comprehensive strategy document at `docs/ideas/strategical/PROFIT_GROWTH_PORTFOLIO_DIVERSIFICATION_STRATEGY.md` (create `docs/ideas/strategical/` dir if missing). No code changes.

---

## 1. Current Portfolio Diagnosis

### 1.1 Concentration Risk Assessment

| SKU | Daily Units | Revenue Share | ROIC | Risk Level |
|-----|------------|---------------|------|------------|
| LINE52_BLACK | 20.4/day | ~42% | 24.4% | **CRITICAL** over-concentration |
| SUIT-61_BLACK | ~8/day | ~17% | ~56% margin | HIGH (single color) |
| LINE51_WHITE | 3.9/day | ~8% | 64.2% | MODERATE |
| T-SHIRT_BLACK | ~8/day | ~5% (low ASP) | ~55% margin | LOW |
| KID-31_BLACK | ~4/day | ~6% | ~67% margin | LOW |
| RUSH-PRO_BLACK | ~3/day | ~2% | thin margin | LOW |
| ELS_PRINTER | sporadic | high ASP spikes | high | N/A (different category) |

**Risk factors:**
- **Gender concentration**: 100% men/kids. Zero women's exposure
- **Color concentration**: BLACK dominates across all SKUs
- **Category concentration**: 100% compression sportswear (plus printer)
- **Single-SKU dominance**: LINE52 = 42% of clothing orders violates the existing 20% max concentration rule in `core/calc/portfolio.py`

### 1.2 Monthly Performance Trajectory (H2 2025 → Jan 2026)

| Month | Orders | Units | Net Rev (KZT) | Profit (KZT) | Margin |
|-------|--------|-------|---------------|---------------|--------|
| Jul-25 | 223 | 234 | 2.78M | 1.25M | 44.8% |
| Aug-25 | 986 | 1,019 | 8.33M | 2.99M | 35.9% |
| Sep-25 | 1,312 | 1,337 | 10.22M | 4.14M | 40.5% |
| Oct-25 | 962 | 972 | 7.46M | 2.59M | 34.8% |
| Nov-25 | 1,249 | 1,274 | 12.00M | 3.90M | 32.5% |
| Dec-25 | 2,035 | 2,111 | 13.08M | 4.60M | 35.2% |
| Jan-26 | 1,720 | 1,762 | 11.30M | 4.63M | 41.0% |

**Annual run-rate profit**: ~50M KZT (~$96K). Capital deployed: 22.4M KZT. **Portfolio ROIC: ~18%/month (LINE51 64%, LINE52 24%, others in between).**

---

## 2. Market Research Findings

### 2.1 Kazakhstan Market Size & Structure

| Metric | Value |
|--------|-------|
| KZ total apparel market (2024) | $5.59B |
| Women's apparel share | $3.01B (54%) |
| Men's apparel share | ~$1.7B (~30%) |
| Children's share | ~16% |
| Online fashion (2024) | $222.7M (10.4% penetration) |
| Online fashion CAGR (to 2028) | 11.9% → 15% penetration |
| Kaspi clothing growth (2024) | **+51% YoY** |
| Kaspi total GMV | KZT 6.0T ($12.5B), +44% |
| Kaspi active merchants | 737,000 |
| Kaspi e-commerce take rate | 11.3% |

### 2.2 Women-vs-Men Spending Reality Check

**The "3x" hypothesis is incorrect.** Actual ratio is **~1.7x** (women 54% vs men ~30% of KZ apparel).

| Source | Women | Men | Ratio |
|--------|-------|-----|-------|
| KZ market share | 54% | ~30% | 1.7x |
| US BLS (2023) | $655/yr | $406/yr | 1.6x |
| Global market share | 51% | 31% | 1.65x |

**However**, the 1.7x ratio still means women's is a $3B market vs $1.7B men's — a $1.3B gap that AcmeWear has zero exposure to.

### 2.3 Wildberries/Ozon Reference Data

| Metric | Value |
|--------|-------|
| Wildberries annual revenue (2024) | $34.4B |
| Wildberries fashion share | 38% ($13.1B) |
| Wildberries women's clothing share | **42% of total marketplace turnover** |
| Wildberries women's Q3 2024 revenue | 113B RUB |
| Wildberries sports category share | 13% of turnover |
| Ozon annual revenue (2024) | $35.5B |
| Russia sportswear market (2024) | $3.87B, CAGR 3.77% |
| Global women's activewear (2025) | $129B, CAGR 8.95% |
| Global compression sportswear | $4.3-4.8B, **CAGR 12.2%** |

### 2.4 KZ Consumer Behavior

- Per capita clothing spend: ~$282/year
- Apparel revenue per capita growth: 4.83% CAGR
- Price sensitivity: HIGH. Sweet spot **$15-40 per item** ("affordable premium")
- **Shymkent**: 36% above-average clothing spend despite 26% below-average income — culture values appearance
- **Astana**: Extreme winters (-15C to -30C) → thermal compression demand
- **Almaty**: Outdoor/fitness culture, yoga/running popular → activewear hub
- Kaspi AOV: ~$50, setting practical ceiling for single-item purchases

---

## 3. Niche Opportunity Matrix (Wildberries→Kaspi Arbitrage)

Research identified 13 niches. Ranked by Kaspi opportunity score:

| Rank | Niche | Kaspi Opp. | Wildberries Demand Signal | Kaspi Competition | Est. Margin |
|------|-------|-----------|-----------------|-------------------|-------------|
| 1 | **Women's workout sets (top+leggings)** | 9/10 | Sets = #1 Wildberries subcategory in costumes | Very few dedicated sellers | 40-60% |
| 2 | **Women's sports bras** | 8/10 | Entry point for women's trust; essential | Very few on Kaspi | 50-65% |
| 3 | **Seamless activewear** | 8/10 | Global trend, "second skin" feel | Absent from Kaspi | 45-60% |
| 4 | **Lightweight running/training sets** | 8/10 | Spring/summer peak demand; running culture growing in Almaty/Astana | Very limited on Kaspi | 40-55% |
| 5 | **Women's compression leggings** | 7/10 | $44.6B global sport legging market | Some sellers, low quality | 40-55% |
| 6 | **Men's compression shorts/tights** | 7/10 | Adjacent to current portfolio | Underserved on Kaspi | 35-50% |
| 7 | **Yoga/pilates clothing** | 7/10 | $80B market by 2033, CAGR 9.5% | Very limited | 45-60% |
| 8 | **Postpartum compression wear** | 7/10 | Medical need, recurring demand | Zero on Kaspi | 50-65% |
| 9 | **Maternity activewear** | 7/10 | Young KZ demographics | Zero on Kaspi | 45-60% |
| 10 | **Compression socks/sleeves** | 6/10 | Good AOV booster, accessory | Very limited | 55-70% |
| 11 | **Kids' sportswear sets** | 5/10 | Already partially served | Some presence | 35-50% |
| 12 | **Plus-size women's activewear** | 5/10 | 6.7B RUB on Wildberries, 30K+ sellers | Sizing risk | 35-50% |
| 13 | **Men's running/cycling compression** | 5/10 | Cycling niche in KZ | Minimal | 35-45% |

### 3.1 Priority Tier Selection

**Tier 1 (Launch immediately, highest conviction):**
- Women's workout sets (compression top + high-waist leggings)
- Women's sports bras (low/medium/high support)
- Women's compression leggings (standalone)

**Rationale**: These three form a complete women's activewear core. On Wildberries, women's clothing = 42% of turnover. Sports bras are the trust entry point. Sets generate $5-20 more profit per order vs singles. These share the same supplier base and fabric technology as current men's compression products.

**Tier 2 (Launch within 2-3 months, spring/summer wave):**
- Seamless activewear (global trend, first-mover advantage on Kaspi)
- Men's compression shorts/tights (natural portfolio extension, summer demand peak)
- Lightweight running/training sets (spring fitness surge, Almaty outdoor culture)

**Tier 3 (Test after Tier 1 proves out):**
- Yoga/pilates clothing
- Postpartum compression
- Maternity activewear
- Compression accessories

---

## 4. Capital Allocation Framework

### 4.1 Risk-Weighted Portfolio Model

Adapting the existing `core/calc/capital_optimizer.py` (which already enforces 20% max concentration per SKU) to a category-level allocation:

**Half-Kelly Position Sizing for New Categories:**
- Win probability for new category: ~60% (conservative estimate based on case studies)
- Win/loss ratio: 2:1 (profitable if >30% sell-through; loss if <10%)
- Full Kelly fraction: (2 × 0.6 - 0.4) / 2 = 40%
- **Half Kelly: 20% of available capital** for the entire women's category entry

**Capital Allocation Targets:**

| Category | Current | Target (6mo) | Target (12mo) |
|----------|---------|--------------|---------------|
| Men's compression (LINE52, SUIT-61, LINE51) | 85% | 55-60% | 40-50% |
| Men's accessories (T-SHIRT, RUSH-PRO) | 10% | 10% | 8-10% |
| Kids (KID-31) | 5% | 5% | 5% |
| **Women's activewear (NEW)** | **0%** | **20-25%** | **30-35%** |
| **Spring/summer lightweight (NEW)** | **0%** | **5-10%** | **5-10%** |

### 4.2 Investment Sizing for Women's Test Launch

Based on Half-Kelly with ~22.4M KZT capital:
- **Max initial allocation**: 4.5M KZT (~$8,600) for women's Tier 1
- **Minimum viable test**: 50-100 units per style × 3 styles = 150-300 units total
- **Sourcing cost per set from China**: $8-20 per unit (compression set)
- **Estimated test investment**: $2,000-4,000 product + $500-1,000 photos/marketing = **$2,500-5,000 total**
- **Maximum acceptable loss** (if 100% unsold): ~$5,000 (2.6M KZT) — 11.6% of capital, within Half-Kelly bounds

### 4.3 Concentration Rules (enforce via existing tools)

| Rule | Threshold | Enforcement |
|------|-----------|-------------|
| Max single SKU_key share | 20% of capital | `portfolio.py:check_concentration_rule()` |
| Max single category share | 50% of capital | NEW rule to add |
| Max single gender share | 70% of capital | NEW rule to add |
| Min category count | 3+ distinct categories | Portfolio diversity check |
| New SKU age factor | 0.50-1.00× based on days | Already in Master_Inventory_Rules_v8 |

---

## 5. Women's Category Entry Playbook

### 5.1 Product Design Principles (NOT "shrink it and pink it")

Research from Gymshark/Under Armour case studies — common failure: resizing men's products and changing colors.

**Required differences from men's line:**
- Body-mapped compression zones (bust, waist, hips vs quads, core)
- Fabric: 220-280 GSM for leggings (squat-proof opacity), 240-320 GSM for sports bras
- Four-way stretch, flatlock seaming (anti-chafe)
- High-waist leggings (dominant silhouette)
- Sports bras: 3 support levels (low, medium, high)
- **Color palette expansion**: Men = 3-4 colors (black, grey, navy). Women need 5-8 per style
  - Core: Black, dark grey, navy
  - Trending 2025: Olive green, soft beige, terracotta, muted pink, burgundy

### 5.2 Size Curve (CIS market)

| Size | Women's Distribution | Test Allocation |
|------|---------------------|-----------------|
| XS | 10% | 5 units |
| S | 25% | 13 units |
| M | 30% | 15 units |
| L | 25% | 13 units |
| XL | 10% | 5 units |
| **Total per style/color** | 100% | **51 units** |

### 5.3 Sourcing

- Same Chinese factory regions as current men's: Guangdong (Guangzhou), Fujian (Quanzhou)
- Suppliers like Hucai, Ingor, Xiamen Top Stones handle both men's and women's
- MOQ negotiation: 50-100 pieces initial "trial order" (higher per-unit cost acceptable)
- Payment: 30% deposit, 70% before shipment
- Women's per-unit cost comparable to men's; sports bras slightly higher (+$1-2/unit)
- Lead time: unchanged at L_days=21

### 5.4 Pricing Strategy

- Target ASP: 8,000-16,000 KZT ($15-30) per item
- Sets (top+leggings): 14,000-22,000 KZT ($27-42)
- Installment psychology: 15,000 KZT set at 3-month Kaspi Red = 5,000 KZT/month
- Minimum 25-30% price gap between single items and sets (avoid cannibalization)
- Budget for 20-25% return rate (vs ~15-18% for men's)

### 5.5 Unit Economics Projection (Women's Compression Set)

```
Sourcing: 70 CNY × 75 FX = 5,250 KZT
Cargo: 1.0 kg × 2.66 USD × 520 FX = 1,383 KZT
COGS_unit = 6,633 KZT

Sell price: 16,000 KZT (set)
Commission (12.5%): 2,000 KZT
Delivery fee: ~699 KZT (5-10K band)
Net after comm+delivery: 13,301 KZT
VAT (4%): 532 KZT
Net_rev_unit = 12,769 KZT

Unit_profit = 12,769 - 6,633 = 6,136 KZT (48.1% margin)
After 22% return adjustment: ~4,786 KZT effective profit
Monthly ROIC (at D_30=3, L=21d, R=10d): ~30%+ → ORDER_FULL gate
```

---

## 6. Go/No-Go Decision Framework

### Phase 1: Pre-Launch Validation (Week 1-2)

| Check | Go | No-Go |
|-------|-----|--------|
| Kaspi search autocomplete for "женские спортивные" | Terms appear | No suggestions |
| Competitor count (women's compression on Kaspi) | <20 sellers | >50 with 100+ reviews each |
| Market-Stat demand estimate | >100 monthly sales | <20 monthly |
| Supplier quotes within budget | COGS < 7,000 KZT/set | COGS > 10,000 KZT/set |
| Unit economics yield >35% margin | Yes | No |

### Phase 2: Test Launch Metrics (Day 1-60)

| Metric | Green (Expand) | Yellow (Continue) | Red (Exit) |
|--------|---------------|-------------------|------------|
| 30-day sell-through | >30% | 15-30% | <10% |
| Return rate | <25% | 25-30% | >35% |
| Review rating | 4.0+ stars | 3.5-4.0 | <3.5 |
| Repeat purchase (60d) | Any repeats | None yet | N/A |
| Ad cost per DB order | <30% of margin | 30-50% | >50% |
| Organic search visibility | Page 1-3 | Page 4-10 | Not appearing |

### Phase 3: Scale Decision (Day 60-90)

- **GREEN across all metrics**: Order 500+ units, expand color/style range, allocate 25% of capital
- **Mixed (some Yellow)**: Test one more month with pricing/photo adjustments, keep at 15% capital
- **Any RED**: Liquidate remaining inventory at 20% discount, redirect capital to proven men's SKUs

---

## 7. Seasonal Strategy Layer

| Quarter | Focus | Capital Action |
|---------|-------|---------------|
| Q1 (Jan-Mar) | Women's core launch + Nauryz gifting. Supplier sampling phase | 20% to women's test |
| Q2 (Apr-Jun) | Spring fitness surge: running sets, lightweight compression. Evaluate test results | Scale to 25% if green |
| Q3 (Jul-Sep) | Peak activewear/summer season. Expand winning styles. Yoga/pilates test | 30% women's if proven. Lightweight peak |
| Q4 (Oct-Dec) | Holiday/gifting season. Evaluate year, plan next seasonal cycle | Consolidate winners, cut losers |

**Spring/summer timing advantage**: Launch women's compression sets in March-April, perfectly aligned with spring fitness motivation (New Year resolution follow-through, pre-summer body prep). Almaty outdoor fitness culture peaks May-September. Running and yoga participation spikes in spring across KZ cities.

---

## 8. Data Processing & Analytics Enhancement

### Existing tools to leverage (no new code in this plan, but flagged for future):

| Tool | Current Use | Adaptation Needed |
|------|------------|------------------|
| `core/calc/portfolio.py` | 20% SKU concentration rule | Add category-level + gender-level caps |
| `core/calc/capital_optimizer.py` | ROIC-based allocation | Add women's category inputs |
| `core/calc/expansion_scorer.py` | KSP→Wildberries scoring | Adapt for "new category" scoring (not just cross-channel) |
| `core/calc/economics.py` | Unit economics | No change needed; works for women's products |
| `scripts/kaspi_marketing_scrape.py` | Ads data | Add new women's campaigns when launched |
| `core/calc/demand_estimator.py` | 30-day demand | No change; will start collecting women's demand data |

### External tools for niche monitoring:
- **Market-Stat (mstat.kz)**: Kaspi demand estimation, 80-85% accuracy. Use for pre-launch validation
- **MPSTATS (mpstats.io)**: Wildberries analytics for cross-referencing demand trends
- **Kaspi search autocomplete**: Manual demand signal collection

---

## 9. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Women's test fails (<10% sell-through) | 30% | Low (Half-Kelly limits loss to 11.6% of capital) | Exit fast, liquidate at discount, redirect capital |
| Higher return rate than expected (>30%) | 25% | Medium | Detailed size charts, customer photos, WhatsApp support |
| Supplier MOQ too high for test | 20% | Low | Negotiate trial order; accept higher per-unit cost |
| Kaspi competition increases before launch | 15% | Medium | Speed to market; launch within 6-8 weeks of approval |
| Men's core demand drops during diversification | 10% | High | Maintain 55%+ capital in proven men's SKUs |
| FX rate shock (CNY/KZT) | 10% | Medium | Existing FX hedging via Binance USDT position |
| Cannibalization of men's set sales | 5% | Low | Different gender = different customer; no overlap |

---

## 10. Execution Timeline

| Week | Action |
|------|--------|
| 1-2 | Pre-launch validation: Kaspi search analysis, Market-Stat demand check, competitor audit |
| 2-3 | Supplier outreach: sample requests for women's compression sets + sports bras (3 styles × 3 colors) |
| 3-5 | Sample review, quality/fit testing, size curve validation |
| 5-6 | Photography (professional model shots + lifestyle), listing creation on Kaspi |
| 6-7 | Production order: 150-300 units (test batch) |
| 7-10 | Shipping from China (L_days=21) |
| 10-11 | Receive inventory, quality check, warehouse |
| 11-12 | **LAUNCH** on Kaspi (all 5 stores) |
| 12-16 | Monitor Phase 2 metrics daily |
| 16 | **GO/NO-GO decision** based on 30-day sell-through |
| 16-20 | If GREEN: Scale order (500+ units), expand colors. If RED: Liquidate |
| 20+ | Begin Tier 2 products (thermal base layers for Q4, seamless activewear) |

---

## Verification

This is a strategy document — no code gates required. Verification:
1. Document passes internal review for logical consistency
2. All market data points are sourced (research agent outputs archived)
3. Unit economics model validated against existing `Master_Inventory_Rules_v8.md` formulas
4. Capital allocation respects existing ROIC gates (20% threshold) and concentration rules (20% max per SKU)
5. Timeline is realistic given existing L_days=21 and current supplier relationships
