#!/usr/bin/env python3
"""
Generate PO Dashboard HTML file from JSON data.
Embeds the JSON data directly into a single-file React webapp.
Supports multiple POs (PO-4 through PO-10) with cascading calculations.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
JSON_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
OUTPUT_PATH = PROJECT_ROOT / "exports" / "po_dashboard.html"


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PO Dashboard</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }
    .container { max-width: 1800px; margin: 0 auto; }

    /* Header with PO selector */
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 12px; }

    /* FX rates in header */
    .fx-rates { display: flex; gap: 16px; align-items: center; font-size: 14px; font-weight: 600; }
    .fx-rate-item { display: flex; align-items: center; gap: 4px; }
    .fx-rate-item label { color: #666; }
    .fx-rate-input { width: 70px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; font-weight: 600; text-align: right; }
    .fx-rate-input:focus { outline: none; border-color: #3b82f6; }

    /* Date headers */
    .date-headers { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px; padding: 12px 16px; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .date-item { display: flex; flex-direction: column; }
    .date-label { font-size: 11px; color: #666; text-transform: uppercase; margin-bottom: 2px; }
    .date-value { font-size: 18px; font-weight: 700; color: #111; }

    /* Export buttons */
    .export-btns { display: flex; gap: 8px; }
    .export-btn { padding: 8px 16px; border: 2px solid #059669; border-radius: 6px; background: white; cursor: pointer; font-size: 12px; font-weight: 600; color: #059669; transition: all 0.2s; }
    .export-btn:hover { background: #ecfdf5; }
    .export-btn.primary { background: #059669; color: white; }
    .export-btn.primary:hover { background: #047857; }
    h1 { color: #333; }
    .po-selector { display: flex; gap: 6px; flex-wrap: wrap; }
    .po-btn { padding: 8px 16px; border: 2px solid #3b82f6; border-radius: 6px; background: white; cursor: pointer; font-size: 13px; font-weight: 600; color: #3b82f6; transition: all 0.2s; }
    .po-btn:hover { background: #eff6ff; }
    .po-btn.active { background: #3b82f6; color: white; }

    .meta { color: #666; font-size: 14px; margin-bottom: 20px; }

    /* Summary Cards */
    .summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
    .card { background: white; border-radius: 8px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .card-label { font-size: 11px; color: #666; margin-bottom: 4px; text-transform: uppercase; }
    .card-value { font-size: 22px; font-weight: 600; color: #333; }
    .card-value.highlight { color: #3b82f6; }
    .card-value.zero { color: #9ca3af; }
    .card-sub { font-size: 10px; color: #9ca3af; margin-top: 4px; }
    .card-sub.bags { font-size: 12px; color: #6b7280; font-weight: 500; }

    /* Totals section */
    .totals-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 20px; padding: 12px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; }
    .totals-title { grid-column: 1 / -1; font-size: 12px; font-weight: 600; color: #166534; margin-bottom: 4px; }
    .totals-item { display: flex; flex-direction: column; }
    .totals-label { font-size: 10px; color: #166534; text-transform: uppercase; }
    .totals-value { font-size: 16px; font-weight: 600; color: #15803d; }

    /* Multiplier input in table */
    .mult-input { width: 55px; padding: 2px 4px; border: 1px solid #d1d5db; border-radius: 3px; font-size: 11px; text-align: right; }
    .mult-input:focus { outline: none; border-color: #3b82f6; background: #eff6ff; }

    /* Size columns */
    th.size-col, td.size-col { min-width: 32px; max-width: 40px; background: #f8fafc; border-left: 1px solid #e5e7eb; }
    th.size-col { font-size: 10px; font-weight: 600; color: #6b7280; }
    td.size-col strong { color: #059669; } /* Green for non-zero qty */

    /* Controls */
    .controls { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
    .search-input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; width: 250px; }
    .filter-btn { padding: 6px 12px; border: 1px solid #ddd; border-radius: 4px; background: white; cursor: pointer; font-size: 12px; }
    .filter-btn.active { background: #3b82f6; border-color: #2563eb; color: white; }
    .tab-btn { padding: 10px 20px; border: none; background: #e5e7eb; cursor: pointer; font-size: 14px; border-radius: 4px 4px 0 0; }
    .tab-btn.active { background: white; font-weight: 500; }

    /* Cutoff date banner */
    .cutoff-banner { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
    .cutoff-date { font-size: 16px; font-weight: 600; color: #4338ca; }
    .info-badge { background: #e0e7ff; border: 1px solid #c7d2fe; padding: 4px 10px; border-radius: 6px; color: #4338ca; font-size: 12px; }
    .warning-badge { background: #fef2f2; border: 1px solid #fecaca; padding: 4px 10px; border-radius: 6px; color: #b91c1c; font-size: 12px; }

    /* Tables */
    .table-container { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; }
    th { background: #f9fafb; padding: 8px 4px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb; cursor: pointer; white-space: nowrap; position: sticky; top: 0; }
    th:hover { background: #f3f4f6; }
    td { padding: 6px 4px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }
    tr:hover { background: #f9fafb; }

    /* Row styles */
    tr.has-order { background: #ecfdf5; }
    tr.has-order:hover { background: #d1fae5; }
    tr.low-roic { background: #fef2f2; }
    tr.low-roic:hover { background: #fee2e2; }
    tr.zero-order { background: #f9fafb; color: #9ca3af; }
    tr.zero-order:hover { background: #f3f4f6; }

    /* Excluded (unapproved) row styling */
    tr.excluded { background: #fff7ed; }
    tr.excluded:hover { background: #ffedd5; }
    tr.excluded td { color: #9a3412; }

    /* Approval toggle checkbox styling */
    .approval-toggle { width: 18px; height: 18px; cursor: pointer; }
    .approval-toggle:disabled { cursor: not-allowed; opacity: 0.3; }

    .roic-high { color: #059669; font-weight: 600; }
    .roic-mid { color: #d97706; font-weight: 500; }
    .roic-low { color: #dc2626; font-weight: 500; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: 500; }
    .badge-confidence { background: #dbeafe; color: #1e40af; }
    .badge-confidence-low { background: #fef3c7; color: #b45309; }
    .badge-oos { background: #fef3c7; color: #b45309; }
    .badge-oos-none { background: #d1fae5; color: #065f46; }
    .badge-no-data { background: #f3f4f6; color: #6b7280; }

    /* Size horizontal table */
    .size-horiz-table th, .size-horiz-table td { text-align: center; min-width: 45px; }
    .size-horiz-table td.sku-col { text-align: left; min-width: 150px; }
    .size-horiz-table .size-val { font-weight: 600; color: #059669; }
    .size-horiz-table .size-val-zero { color: #d1d5db; }

    /* Tooltip */
    .tooltip { position: relative; cursor: help; }
    .tooltip:hover::after { content: attr(data-tip); position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: #1f2937; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap; z-index: 10; }

    /* Responsive */
    @media (max-width: 768px) {
      .controls { flex-direction: column; align-items: stretch; }
      .search-input { width: 100%; }
      .header { flex-direction: column; align-items: flex-start; }
    }
  </style>
</head>
<body>
  <div id="root"></div>

  <script type="text/babel">
    // Embed data directly - generated by generate_po_dashboard_data.py
    const DATA = __JSON_DATA__;

    const { useState, useMemo, useEffect, useCallback } = React;

    // All possible sizes in order (canonical)
    const SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '22', '24', '26', '28', '30', '32', 'ONE_SIZE', 'ONESIZE', 'OS'];
    const SIZE_RANK = SIZE_ORDER.reduce((acc, s, idx) => {
      acc[s] = idx;
      return acc;
    }, {});

    const normalizeSize = (size) => {
      if (!size) return '';
      return String(size).toUpperCase().replace(/\s+/g, '').replace(/-/g, '');
    };

    const sizeRank = (size) => {
      const s = normalizeSize(size);
      if (SIZE_RANK[s] !== undefined) return SIZE_RANK[s];
      const num = parseInt(s, 10);
      if (!Number.isNaN(num)) return 100 + num;
      return 999;
    };

    // LocalStorage helpers
    const loadFromStorage = (key, defaultValue) => {
      try {
        const saved = localStorage.getItem(key);
        return saved ? JSON.parse(saved) : defaultValue;
      } catch { return defaultValue; }
    };
    const saveToStorage = (key, value) => {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
    };

    // Get today's date in local format
    const getTodayDate = () => new Date().toISOString().split('T')[0];

    function DateHeaders({ poData, activePO, isApproved }) {
      const { po_message_date, po_send_date, est_arr_date, summary } = poData;
      const overridePrepDays = poData?.po_name === 'PO-5' ? poData.prep_days_clothes : null;
      const prepDays = (Number.isFinite(overridePrepDays) && overridePrepDays > 0)
        ? overridePrepDays
        : (summary?.avg_prep_days || poData.sku_level?.[0]?.prep_days || 5);

      // Calculate separate prep days for Clothes (CL_) and Electronics (ELS_)
      const { clothesPrepDays, elsPrepDays } = useMemo(() => {
        const approvedItems = (poData.sku_level || []).filter(s =>
          s.po_qty_total > 0 && isApproved(activePO, s.sku_key)
        );

        // Separate CL and ELS items
        const clItems = approvedItems.filter(s => s.sku_key.startsWith('CL_'));
        const elsItems = approvedItems.filter(s => s.sku_key.startsWith('ELS_'));

        // Clothes prep: override for PO-5, otherwise ceil(1.3 * total_weight_kg / 100)
        const totalClWeight = clItems.reduce((sum, s) => sum + (s.po_weight_kg || 0), 0);
        const clothesPrep = (Number.isFinite(overridePrepDays) && overridePrepDays > 0)
          ? overridePrepDays
          : (totalClWeight > 0 ? Math.ceil(1.3 * totalClWeight / 100) : 0);

        // Electronics prep: always 1 if any ELS items approved with orders
        const elsPrep = elsItems.length > 0 ? 1 : 0;

        return { clothesPrepDays: clothesPrep, elsPrepDays: elsPrep };
      }, [poData, activePO, isApproved]);

      return (
        <div className="date-headers">
          <div className="date-item">
            <span className="date-label">Today</span>
            <span className="date-value">{getTodayDate()}</span>
          </div>
          <div className="date-item">
            <span className="date-label">Message Date</span>
            <span className="date-value">{po_message_date}</span>
          </div>
          <div className="date-item">
            <span className="date-label">Prep Days</span>
            <span className="date-value">{prepDays}</span>
          </div>
          <div className="date-item">
            <span className="date-label" title="Prep days for approved clothes (CL)">CL Prep</span>
            <span className="date-value" style={{color: clothesPrepDays > 0 ? '#059669' : '#9ca3af'}}>{clothesPrepDays}</span>
          </div>
          <div className="date-item">
            <span className="date-label" title="Prep days for approved electronics (ELS)">ELS Prep</span>
            <span className="date-value" style={{color: elsPrepDays > 0 ? '#059669' : '#9ca3af'}}>{elsPrepDays}</span>
          </div>
          <div className="date-item">
            <span className="date-label">Cargo Send</span>
            <span className="date-value">{po_send_date}</span>
          </div>
          <div className="date-item">
            <span className="date-label">Arrival</span>
            <span className="date-value">{est_arr_date}</span>
          </div>
        </div>
      );
    }

    function CutoffBanner({ poData }) {
      const { summary, po_name, po_message_date, stock_date, cutoff_date, est_arr_date } = poData;
      return (
        <div className="cutoff-banner">
          <div>
            <span className="cutoff-date">{po_name}</span>
            <span style={{marginLeft: '16px', color: '#666', fontSize: '13px'}}>
              Stock: {stock_date} | Data cutoff: {cutoff_date}
            </span>
          </div>
          <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap'}}>
            {summary.skus_with_orders > 0 && (
              <span className="info-badge">{summary.skus_with_orders} need PO</span>
            )}
            {summary.no_demand_estimate > 0 && (
              <span className="warning-badge">{summary.no_demand_estimate} no demand</span>
            )}
            {summary.low_roic_skus > 0 && (
              <span className="warning-badge">{summary.low_roic_skus} low ROIC</span>
            )}
          </div>
        </div>
      );
    }

    function SummaryCards({ poData, activePO, isApproved }) {
      const { po_name, lead_time_L, reorder_cycle_R } = poData;

      // Calculate summary based on approved SKUs only
      const approvedSummary = useMemo(() => {
        const allSkus = poData.sku_level || [];
        const approvedSkuLevel = allSkus.filter(s => isApproved(activePO, s.sku_key));
        const approvedWithOrders = approvedSkuLevel.filter(s => s.po_qty_total > 0);

        return {
          total_skus: allSkus.length,
          skus_with_orders: approvedWithOrders.length,
          skus_without_orders: approvedSkuLevel.length - approvedWithOrders.length,
          total_units: approvedWithOrders.reduce((sum, s) => sum + s.po_qty_total, 0),
          total_weight_kg: approvedWithOrders.reduce((sum, s) => sum + (s.po_weight_kg || 0), 0)
        };
      }, [poData, activePO, isApproved]);

      const bagsQty = Math.ceil((approvedSummary.total_weight_kg || 0) / 65);
      return (
        <div className="summary-cards">
          <div className="card">
            <div className="card-label">Total SKUs</div>
            <div className="card-value">{approvedSummary.total_skus}</div>
            <div className="card-sub">{approvedSummary.skus_with_orders} approved / {approvedSummary.skus_without_orders} OK</div>
          </div>
          <div className="card">
            <div className="card-label">Units to Order</div>
            <div className="card-value highlight">{approvedSummary.total_units.toLocaleString()}</div>
          </div>
          <div className="card">
            <div className="card-label">Total Weight</div>
            <div className="card-value">{approvedSummary.total_weight_kg.toLocaleString()} kg</div>
            <div className="card-sub bags">{bagsQty} bags</div>
          </div>
          <div className="card">
            <div className="card-label">Lead Time (L)</div>
            <div className="card-value">{lead_time_L} days</div>
          </div>
          <div className="card">
            <div className="card-label">Reorder Cycle (R)</div>
            <div className="card-value">{reorder_cycle_R} days</div>
          </div>
        </div>
      );
    }

    function TotalsSection({ poData, fxRates, activePO, isApproved }) {
      // Calculate totals filtered by ROIC >= 10% AND approved
      const totals = useMemo(() => {
        const items = (poData.sku_level || []).filter(s =>
          s.po_qty_total > 0 &&
          s.roic_pct >= 10 &&
          isApproved(activePO, s.sku_key)
        );
        return {
          po_base_cost_cny: items.reduce((sum, s) => sum + (s.po_base_cost_cny || 0), 0),
          po_base_cost_kzt: items.reduce((sum, s) => sum + (s.po_base_cost_kzt || 0), 0),
          po_dlv_usd: items.reduce((sum, s) => sum + (s.po_dlv_usd || 0), 0),
          po_dlv_kzt: items.reduce((sum, s) => sum + (s.po_dlv_kzt || 0), 0),
          po_cogs_kzt: items.reduce((sum, s) => sum + (s.po_cogs_kzt || 0), 0),
          count: items.length
        };
      }, [poData, activePO, isApproved]);

      return (
        <div className="totals-section">
          <div className="totals-title">PO Totals (Approved + ROIC ≥ 10%, {totals.count} SKUs)</div>
          <div className="totals-item">
            <span className="totals-label">Base Cost (CNY)</span>
            <span className="totals-value">¥{totals.po_base_cost_cny.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
          </div>
          <div className="totals-item">
            <span className="totals-label">Base Cost (KZT)</span>
            <span className="totals-value">₸{totals.po_base_cost_kzt.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
          </div>
          <div className="totals-item">
            <span className="totals-label">Delivery (USD)</span>
            <span className="totals-value">${totals.po_dlv_usd.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
          </div>
          <div className="totals-item">
            <span className="totals-label">Delivery (KZT)</span>
            <span className="totals-value">₸{totals.po_dlv_kzt.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
          </div>
          <div className="totals-item">
            <span className="totals-label">Total COGS (KZT)</span>
            <span className="totals-value">₸{totals.po_cogs_kzt.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
          </div>
        </div>
      );
    }

    // Export functions using SheetJS
    function exportCurrentPO(poData, poName, isApproved) {
      const wb = XLSX.utils.book_new();

      // Sheet 1: SKU Level (with Approved column)
      const skuData = (poData.sku_level || []).map(s => ({
        'Approved': isApproved(poName, s.sku_key) ? 'Yes' : 'No',
        'SKU Key': s.sku_key,
        'SKU Name': s.sku_name,
        'Stock': s.stock,
        'Inbound': s.inbound,
        'Pre-Arrival': s.pre_arrival,
        'D/day': s.d_sku,
        'T_post': s.t_post_days,
        'Target': s.target,
        'Order Qty': s.po_qty_total,
        'Weight (kg)': s.po_weight_kg,
        'PO COGS': s.po_cogs_kzt,
        'ROIC %': s.roic_pct,
        'Margin %': s.profit_margin_pct,
        'Msg Date': s.po_message_date,
        'Send Date': s.po_send_date,
        'Est ARR': s.est_arr_date
      }));
      const ws1 = XLSX.utils.json_to_sheet(skuData);
      XLSX.utils.book_append_sheet(wb, ws1, 'SKU Level');

      // Sheet 2: Size Level
      const sizeData = (poData.size_level || []).map(s => ({
        'SKU Key': s.sku_key,
        'Size': s.size,
        'Stock': s.stock,
        'Pre-Arrival': s.pre_arrival,
        'D/day': s.d_size,
        'Target': s.target,
        'Order Qty': s.order_qty,
        'Weight (kg)': s.weight_kg,
        'PO COGS': s.po_cogs_kzt,
        'ROIC %': s.roic_pct
      }));
      const ws2 = XLSX.utils.json_to_sheet(sizeData);
      XLSX.utils.book_append_sheet(wb, ws2, 'Size Level');

      // Sheet 3: Size Horizontal
      const horizData = (poData.size_horizontal || []).map(s => {
        const row = {
          'SKU Key': s.sku_key,
          'SKU Name': s.sku_name,
          'D/day': s.d_sku,
          'Total': s.po_qty_total
        };
        if (s.size_orders) {
          SIZE_ORDER.forEach(size => {
            if (s.size_orders[size]) row[size] = s.size_orders[size];
          });
        }
        return row;
      });
      const ws3 = XLSX.utils.json_to_sheet(horizData);
      XLSX.utils.book_append_sheet(wb, ws3, 'Size Horizontal');

      // Sheet 4: Master Params (economics)
      const sizeStockMap = {};
      const sizeSet = new Set();
      (poData.size_level || []).forEach(row => {
        if (!row.size) return;
        sizeSet.add(row.size);
        if (!sizeStockMap[row.sku_key]) sizeStockMap[row.sku_key] = {};
        const current = sizeStockMap[row.sku_key][row.size] || 0;
        sizeStockMap[row.sku_key][row.size] = current + (row.stock || 0);
      });
      const sizeExtras = Array.from(sizeSet).filter(s => SIZE_RANK[s] === undefined).sort();
      const masterSizes = [
        ...SIZE_ORDER.filter(s => sizeSet.has(s)),
        ...sizeExtras
      ];

      const masterData = (poData.sku_level || []).map(s => {
        const row = {
          'SKU Key': s.sku_key,
          'D/day (Initial)': s.d_sku,
          'Base Cost (CNY)': s.base_cost_cny,
          'Weight/Unit (kg)': s.weight_per_unit_kg,
          'Unit COGS (KZT)': s.unit_cogs,
          'Avg Sell Price': s.avg_sell_price,
          'Net Rev/Unit': s.net_revenue_unit,
          'Profit/Unit': s.profit_unit,
          'PO Base (CNY)': s.po_base_cost_cny,
          'PO Base (KZT)': s.po_base_cost_kzt,
          'PO Dlv (USD)': s.po_dlv_usd,
          'PO Dlv (KZT)': s.po_dlv_kzt,
          'PO COGS (KZT)': s.po_cogs_kzt,
          'Monthly Profit': s.monthly_profit,
          'K_avg': s.k_avg,
          'ROIC %': s.roic_pct,
          'Margin %': s.profit_margin_pct
        };
        masterSizes.forEach(size => {
          row[`Stock ${size}`] = sizeStockMap[s.sku_key]?.[size] || 0;
        });
        return row;
      });
      const ws4 = XLSX.utils.json_to_sheet(masterData);
      XLSX.utils.book_append_sheet(wb, ws4, 'Master Params');

      // Download
      const dateStr = getTodayDate().replace(/-/g, '');
      XLSX.writeFile(wb, `${poName}_Export_${dateStr}.xlsx`);
    }

    function exportAllPOs(allPOs, isApproved) {
      const wb = XLSX.utils.book_new();
      const poNames = Object.keys(allPOs).sort();

      // Sheet 1: First PO's SKU level data (with Approved column)
      if (poNames.length > 0) {
        const firstPO = allPOs[poNames[0]];
        const skuData = (firstPO.sku_level || []).map(s => ({
          'Approved': isApproved(poNames[0], s.sku_key) ? 'Yes' : 'No',
          'PO': poNames[0],
          'SKU Key': s.sku_key,
          'SKU Name': s.sku_name,
          'Order Qty': s.po_qty_total,
          'Weight (kg)': s.po_weight_kg,
          'PO COGS': s.po_cogs_kzt,
          'ROIC %': s.roic_pct
        }));
        const ws1 = XLSX.utils.json_to_sheet(skuData);
        XLSX.utils.book_append_sheet(wb, ws1, poNames[0]);
      }

      // Sheet 2: All POs concatenated (with Approved column)
      const allData = [];
      poNames.forEach(poName => {
        const poData = allPOs[poName];
        (poData.sku_level || []).forEach(s => {
          if (s.po_qty_total > 0) {
            allData.push({
              'Approved': isApproved(poName, s.sku_key) ? 'Yes' : 'No',
              'PO': poName,
              'SKU Key': s.sku_key,
              'SKU Name': s.sku_name,
              'Stock': s.stock,
              'Pre-Arrival': s.pre_arrival,
              'D/day': s.d_sku,
              'Order Qty': s.po_qty_total,
              'Weight (kg)': s.po_weight_kg,
              'PO COGS': s.po_cogs_kzt,
              'ROIC %': s.roic_pct,
              'Margin %': s.profit_margin_pct,
              'Msg Date': s.po_message_date,
              'Est ARR': s.est_arr_date
            });
          }
        });
      });
      const ws2 = XLSX.utils.json_to_sheet(allData);
      XLSX.utils.book_append_sheet(wb, ws2, 'All POs');

      // Download
      const dateStr = getTodayDate().replace(/-/g, '');
      XLSX.writeFile(wb, `PO_Dashboard_Export_${dateStr}.xlsx`);
    }

    function ROICBadge({ roic }) {
      if (roic === 0) return <span style={{color:'#9ca3af'}}>-</span>;
      let className = roic >= 20 ? 'roic-high' : roic >= 15 ? 'roic-mid' : 'roic-low';
      return <span className={className}>{roic.toFixed(1)}%</span>;
    }

    function ConfidenceBadge({ confidence }) {
      if (!confidence || confidence === 'NO_DATA') return <span className="badge badge-no-data">NO DATA</span>;
      const cls = confidence === 'HIGH' ? 'badge-confidence' : 'badge-confidence-low';
      return <span className={`badge ${cls}`}>{confidence}</span>;
    }

    function OOSBadge({ oosType }) {
      if (!oosType || oosType === 'NONE') return <span className="badge badge-oos-none">OK</span>;
      return <span className="badge badge-oos">{oosType}</span>;
    }

    function DOCCell({ doc, d }) {
      if (!d || d === 0) return <span style={{color:'#9ca3af'}}>-</span>;
      const val = doc || 0;
      const cls = val >= 30 ? 'roic-high' : val >= 14 ? 'roic-mid' : 'roic-low';
      return <span className={cls}>{val.toFixed(1)}</span>;
    }

    function SKUTable({ poData, search, filterMode, sortConfig, onSort, multipliers, onMultiplierChange, activePO, isApproved, onApprovalChange, lockSort, lockedSkuOrder }) {
      const filtered = useMemo(() => {
        let items = poData.sku_level || [];

        // Filter by mode
        if (filterMode === 'need_po') items = items.filter(s => s.po_qty_total > 0);
        else if (filterMode === 'zero') items = items.filter(s => s.po_qty_total === 0);

        // Search filter
        if (search) {
          const q = search.toLowerCase();
          items = items.filter(s =>
            s.sku_key.toLowerCase().includes(q) ||
            s.sku_name.toLowerCase().includes(q) ||
            (s.notes && s.notes.toLowerCase().includes(q))
          );
        }

        // Sort
        if (lockSort && lockedSkuOrder && lockedSkuOrder.length > 0) {
          const orderIndex = new Map(lockedSkuOrder.map((k, i) => [k, i]));
          items = [...items].sort((a, b) => {
            const aIdx = orderIndex.get(a.sku_key);
            const bIdx = orderIndex.get(b.sku_key);
            if (aIdx == null && bIdx == null) return 0;
            if (aIdx == null) return 1;
            if (bIdx == null) return -1;
            return aIdx - bIdx;
          });
        } else if (sortConfig.key) {
          items = [...items].sort((a, b) => {
            let aVal = a[sortConfig.key];
            let bVal = b[sortConfig.key];
            if (aVal == null) aVal = sortConfig.key.includes('date') ? '9999-99-99' : -Infinity;
            if (bVal == null) bVal = sortConfig.key.includes('date') ? '9999-99-99' : -Infinity;
            if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        return items;
      }, [poData, search, filterMode, sortConfig, lockSort, lockedSkuOrder]);

      const handleSort = (key) => {
        onSort({
          key,
          dir: sortConfig.key === key && sortConfig.dir === 'asc' ? 'desc' : 'asc'
        });
      };

      const SortHeader = ({ field, children, title }) => (
        <th onClick={() => handleSort(field)} title={title}>
          {children} {sortConfig.key === field ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
        </th>
      );

      return (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <SortHeader field="sku_name" title="SKU Name">SKU Name</SortHeader>
                <th style={{width: '60px'}} title="Toggle to include/exclude from PO">Appr</th>
                <SortHeader field="stock" title="Current stock">Stock</SortHeader>
                <SortHeader field="inbound" title="Snapshot inbound (from DB)">Snap_Inb</SortHeader>
                <SortHeader field="active_inbound" title="POs arriving between msg and arr dates">Act_Inb</SortHeader>
                <SortHeader field="inbound_total" title="All POs arriving before arr date">Inb_Tot</SortHeader>
                <SortHeader field="days_until_arrival" title="Days from msg_date to arrival">Days→Arr</SortHeader>
                <SortHeader field="consumption_until_arrival" title="Consumption from msg_date to arrival">Cons→Arr</SortHeader>
                <SortHeader field="pre_arrival" title="Projected stock at PO arrival">Pre-Arr</SortHeader>
                <SortHeader field="d_sku" title="Daily demand (blended)">D/day</SortHeader>
                <th title="Demand multiplier (editable)">Mult</th>
                <th title="D/day × Multiplier">D×Mult</th>
                <SortHeader field="t_post_days" title="Target coverage days post-arrival">T_Post</SortHeader>
                <SortHeader field="target" title="Target stock post-arrival">Target</SortHeader>
                <SortHeader field="rop_total" title="Reorder point">ROP</SortHeader>
                <SortHeader field="po_qty_total" title="Order quantity">Order</SortHeader>
                <SortHeader field="po_cogs_kzt" title="PO COGS (KZT)">PO COGS</SortHeader>
                <SortHeader field="po_weight_kg" title="Order weight">Weight</SortHeader>
                <SortHeader field="po_message_date" title="Message date">Msg Date</SortHeader>
                <SortHeader field="prep_days" title="Prep days">Prep</SortHeader>
                <SortHeader field="po_send_date" title="Cargo send date">Send Date</SortHeader>
                <SortHeader field="est_arr_date" title="Estimated arrival date">Est ARR</SortHeader>
                <SortHeader field="pre_arr_doc" title="Days of coverage before arrival">Pre DOC</SortHeader>
                <SortHeader field="post_arr_doc" title="Days of coverage after order arrives">Post DOC</SortHeader>
                <SortHeader field="monthly_profit" title="Monthly profit">Mon.Profit</SortHeader>
                <SortHeader field="k_avg" title="Avg invested capital">K_avg</SortHeader>
                <SortHeader field="roic_pct" title="Return on invested capital">ROIC</SortHeader>
                <SortHeader field="profit_margin_pct" title="Profit margin %">Margin%</SortHeader>
                <SortHeader field="availability_score" title="Stock availability (0-1)">Avail</SortHeader>
                <th>Conf</th>
                <th>OOS</th>
                <th>Notes</th>
                {/* Size columns */}
                {SIZE_ORDER.map(size => (
                  <th key={size} className="size-col" title={`Order qty for size ${size}`}>{size}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => {
                const approved = isApproved(activePO, row.sku_key);
                const rowClass = !approved && row.po_qty_total > 0 ? 'excluded' :
                                 row.po_qty_total === 0 ? 'zero-order' :
                                 row.roic_below_threshold ? 'low-roic' : 'has-order';
                const mult = multipliers?.[row.sku_key] || 1.0;
                const dMult = (row.d_sku || 0) * mult;
                return (
                  <tr key={row.sku_key} className={rowClass}>
                    <td>
                      <strong>{row.sku_name}</strong><br/>
                      <small style={{color:'#9ca3af'}}>{row.sku_key}</small>
                    </td>
                    <td style={{textAlign: 'center'}}>
                      <input
                        type="checkbox"
                        className="approval-toggle"
                        checked={approved}
                        onChange={(e) => onApprovalChange(activePO, row.sku_key, e.target.checked)}
                        disabled={row.po_qty_total === 0}
                      />
                    </td>
                    <td>{row.stock}</td>
                    <td>{row.inbound}</td>
                    <td>{row.active_inbound || 0}</td>
                    <td>{row.inbound_total || 0}</td>
                    <td>{row.days_until_arrival}</td>
                    <td>{row.consumption_until_arrival?.toFixed(1) || '-'}</td>
                    <td>{row.pre_arrival}</td>
                    <td className="tooltip" data-tip={`Anchor: ${row.d_anchor?.toFixed(2)}, Model: ${row.d_model?.toFixed(2)}, w: ${row.anchor_weight?.toFixed(2)}`}>
                      <strong>{row.d_sku?.toFixed(2) || '-'}</strong>
                    </td>
                    <td>
                      <input
                        type="number"
                        className="mult-input"
                        value={mult}
                        onChange={e => onMultiplierChange(row.sku_key, e.target.value)}
                        step="0.1"
                        min="0"
                      />
                    </td>
                    <td><strong>{dMult.toFixed(2)}</strong></td>
                    <td>{row.t_post_days?.toFixed(0) || '-'}</td>
                    <td>{row.target?.toFixed(0) || '-'}</td>
                    <td>{row.rop_total?.toFixed(0) || '-'}</td>
                    <td><strong style={{fontSize:'13px'}}>{row.po_qty_total}</strong></td>
                    <td>₸{row.po_cogs_kzt?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>{row.po_weight_kg?.toFixed(1)} kg</td>
                    <td>{row.po_message_date}</td>
                    <td>{row.prep_days}</td>
                    <td>{row.po_send_date}</td>
                    <td>{row.est_arr_date}</td>
                    <td><DOCCell doc={row.pre_arr_doc} d={row.d_sku} /></td>
                    <td><DOCCell doc={row.post_arr_doc} d={row.d_sku} /></td>
                    <td>{row.monthly_profit?.toLocaleString() || '-'}</td>
                    <td>{row.k_avg?.toLocaleString() || '-'}</td>
                    <td><ROICBadge roic={row.roic_pct} /></td>
                    <td>{row.profit_margin_pct?.toFixed(1) || '-'}%</td>
                    <td>{row.availability_score > 0 ? (row.availability_score * 100).toFixed(0) + '%' : '-'}</td>
                    <td><ConfidenceBadge confidence={row.confidence} /></td>
                    <td><OOSBadge oosType={row.oos_type} /></td>
                    <td style={{maxWidth:'120px', fontSize:'10px', color:'#6b7280', whiteSpace:'normal'}}>{row.notes}</td>
                    {/* Size order quantities */}
                    {SIZE_ORDER.map(size => {
                      const sizeOrders = row.size_orders || {};
                      const qty = sizeOrders[size] || sizeOrders[size.toUpperCase()] || 0;
                      return (
                        <td key={size} className="size-col" style={{textAlign: 'center', fontSize: '11px'}}>
                          {qty > 0 ? <strong>{qty}</strong> : '-'}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div style={{padding: '40px', textAlign: 'center', color: '#9ca3af'}}>
              No SKUs match the current filters
            </div>
          )}
        </div>
      );
    }

    function SizeTable({ poData, search, filterMode, sortConfig, onSort, lockSort, lockedSkuOrder }) {
      const filtered = useMemo(() => {
        let items = poData.size_level || [];

        if (filterMode === 'need_po') items = items.filter(s => s.order_qty > 0);
        else if (filterMode === 'zero') items = items.filter(s => s.order_qty === 0);

        if (search) {
          const q = search.toLowerCase();
          items = items.filter(s =>
            s.sku_key.toLowerCase().includes(q) ||
            s.size.toLowerCase().includes(q)
          );
        }

        if (lockSort && lockedSkuOrder && lockedSkuOrder.length > 0) {
          const orderIndex = new Map(lockedSkuOrder.map((k, i) => [k, i]));
          items = [...items].sort((a, b) => {
            const aIdx = orderIndex.get(a.sku_key);
            const bIdx = orderIndex.get(b.sku_key);
            if (aIdx == null && bIdx == null) return sizeRank(a.size) - sizeRank(b.size);
            if (aIdx == null) return 1;
            if (bIdx == null) return -1;
            if (aIdx !== bIdx) return aIdx - bIdx;
            return sizeRank(a.size) - sizeRank(b.size);
          });
        } else if (sortConfig.key) {
          items = [...items].sort((a, b) => {
            if (sortConfig.key === 'size') {
              return sortConfig.dir === 'asc'
                ? sizeRank(a.size) - sizeRank(b.size)
                : sizeRank(b.size) - sizeRank(a.size);
            }
            const aVal = a[sortConfig.key];
            const bVal = b[sortConfig.key];
            if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1;
            if (a.sku_key === b.sku_key) {
              return sizeRank(a.size) - sizeRank(b.size);
            }
            return 0;
          });
        }
        return items;
      }, [poData, search, filterMode, sortConfig, lockSort, lockedSkuOrder]);

      const handleSort = (key) => {
        onSort({
          key,
          dir: sortConfig.key === key && sortConfig.dir === 'asc' ? 'desc' : 'asc'
        });
      };

      const SortHeader = ({ field, children, title }) => (
        <th onClick={() => handleSort(field)} title={title}>
          {children} {sortConfig.key === field ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
        </th>
      );

      return (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <SortHeader field="sku_key" title="SKU Key">SKU</SortHeader>
                <SortHeader field="size" title="Size">Size</SortHeader>
                <SortHeader field="stock" title="Current stock">Stock</SortHeader>
                <SortHeader field="inbound" title="Snapshot inbound (from DB)">Snap_Inb</SortHeader>
                <SortHeader field="active_inbound" title="POs arriving between msg and arr dates">Act_Inb</SortHeader>
                <SortHeader field="inbound_total" title="All POs arriving before arr date">Inb_Tot</SortHeader>
                <SortHeader field="days_until_arrival" title="Days from msg_date to arrival">Days→Arr</SortHeader>
                <SortHeader field="consumption_until_arrival" title="Consumption from msg_date to arrival">Cons→Arr</SortHeader>
                <SortHeader field="pre_arrival" title="Pre-arrival stock">Pre-Arr</SortHeader>
                <SortHeader field="d_size" title="Daily demand">D/day</SortHeader>
                <SortHeader field="t_post_days" title="Target coverage days">T_Post</SortHeader>
                <SortHeader field="target" title="Target stock">Target</SortHeader>
                <SortHeader field="rop_size" title="Reorder point">ROP</SortHeader>
                <SortHeader field="order_qty" title="Order quantity">Order</SortHeader>
                <SortHeader field="po_cogs_kzt" title="PO COGS (KZT)">PO COGS</SortHeader>
                <SortHeader field="weight_kg" title="Weight">Weight</SortHeader>
                <SortHeader field="po_message_date" title="Message date">Msg Date</SortHeader>
                <SortHeader field="prep_days" title="Prep days">Prep</SortHeader>
                <SortHeader field="po_send_date" title="Send date">Send Date</SortHeader>
                <SortHeader field="est_arr_date" title="Est arrival">Est ARR</SortHeader>
                <SortHeader field="pre_arr_doc" title="Pre-arrival DOC">Pre DOC</SortHeader>
                <SortHeader field="post_arr_doc" title="Post-arrival DOC">Post DOC</SortHeader>
                <SortHeader field="roic_pct" title="ROIC">ROIC</SortHeader>
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => {
                const rowClass = row.order_qty === 0 ? 'zero-order' : 'has-order';
                return (
                  <tr key={row.sku_id} className={rowClass}>
                    <td><small>{row.sku_key}</small></td>
                    <td><strong>{row.size}</strong></td>
                    <td>{row.stock}</td>
                    <td>{row.inbound}</td>
                    <td>{row.active_inbound || 0}</td>
                    <td>{row.inbound_total || 0}</td>
                    <td>{row.days_until_arrival}</td>
                    <td>{row.consumption_until_arrival?.toFixed(1) || '-'}</td>
                    <td>{row.pre_arrival}</td>
                    <td>{row.d_size?.toFixed(2) || '-'}</td>
                    <td>{row.t_post_days?.toFixed(0) || '-'}</td>
                    <td>{row.target?.toFixed(0) || '-'}</td>
                    <td>{row.rop_size?.toFixed(0) || '-'}</td>
                    <td><strong>{row.order_qty}</strong></td>
                    <td>₸{row.po_cogs_kzt?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>{row.weight_kg?.toFixed(2)} kg</td>
                    <td>{row.po_message_date}</td>
                    <td>{row.prep_days}</td>
                    <td>{row.po_send_date}</td>
                    <td>{row.est_arr_date}</td>
                    <td><DOCCell doc={row.pre_arr_doc} d={row.d_size} /></td>
                    <td><DOCCell doc={row.post_arr_doc} d={row.d_size} /></td>
                    <td><ROICBadge roic={row.roic_pct} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
    }

    function SizeHorizontalTable({ poData, search, filterMode, sortConfig, onSort, lockSort, lockedSkuOrder }) {
      const items = poData.size_horizontal || [];

      // Get all unique sizes across all SKUs
      const allSizes = useMemo(() => {
        const sizeSet = new Set();
        items.forEach(row => {
          if (row.size_orders) {
            Object.keys(row.size_orders).forEach(s => sizeSet.add(s));
          }
        });
        // Sort by SIZE_ORDER
        return SIZE_ORDER.filter(s => sizeSet.has(s));
      }, [items]);

      const filtered = useMemo(() => {
        let result = items;

        if (filterMode === 'need_po') result = result.filter(s => s.po_qty_total > 0);
        else if (filterMode === 'zero') result = result.filter(s => s.po_qty_total === 0);

        if (search) {
          const q = search.toLowerCase();
          result = result.filter(s =>
            s.sku_key.toLowerCase().includes(q) ||
            s.sku_name.toLowerCase().includes(q)
          );
        }

        if (lockSort && lockedSkuOrder && lockedSkuOrder.length > 0) {
          const orderIndex = new Map(lockedSkuOrder.map((k, i) => [k, i]));
          result = [...result].sort((a, b) => {
            const aIdx = orderIndex.get(a.sku_key);
            const bIdx = orderIndex.get(b.sku_key);
            if (aIdx == null && bIdx == null) return 0;
            if (aIdx == null) return 1;
            if (bIdx == null) return -1;
            return aIdx - bIdx;
          });
        } else if (sortConfig.key) {
          result = [...result].sort((a, b) => {
            const aVal = a[sortConfig.key];
            const bVal = b[sortConfig.key];
            if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        return result;
      }, [items, search, filterMode, sortConfig, lockSort, lockedSkuOrder]);

      const handleSort = (key) => {
        onSort({
          key,
          dir: sortConfig.key === key && sortConfig.dir === 'asc' ? 'desc' : 'asc'
        });
      };

      return (
        <div className="table-container">
          <table className="size-horiz-table">
            <thead>
              <tr>
                <th onClick={() => handleSort('sku_name')} style={{textAlign:'left'}}>
                  SKU {sortConfig.key === 'sku_name' ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
                </th>
                <th onClick={() => handleSort('d_sku')} title="Daily demand">
                  D/day {sortConfig.key === 'd_sku' ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
                </th>
                <th onClick={() => handleSort('po_qty_total')} title="Total order qty">
                  Total {sortConfig.key === 'po_qty_total' ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
                </th>
                {allSizes.map(size => (
                  <th key={size}>{size}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => {
                const rowClass = row.po_qty_total === 0 ? 'zero-order' : 'has-order';
                return (
                  <tr key={row.sku_key} className={rowClass}>
                    <td className="sku-col">
                      <strong>{row.sku_name}</strong><br/>
                      <small style={{color:'#9ca3af'}}>{row.sku_key}</small>
                    </td>
                    <td>{row.d_sku?.toFixed(2) || '-'}</td>
                    <td><strong>{row.po_qty_total}</strong></td>
                    {allSizes.map(size => {
                      const qty = row.size_orders?.[size] || 0;
                      return (
                        <td key={size} className={qty > 0 ? 'size-val' : 'size-val-zero'}>
                          {qty > 0 ? qty : '-'}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div style={{padding: '40px', textAlign: 'center', color: '#9ca3af'}}>
              No SKUs match the current filters
            </div>
          )}
        </div>
      );
    }

    function MasterParamsTable({ poData, search, sortConfig, onSort, lockSort, lockedSkuOrder }) {
      const sizeStockMap = useMemo(() => {
        const map = new Map();
        (poData.size_level || []).forEach(row => {
          if (!row.size) return;
          if (!map.has(row.sku_key)) map.set(row.sku_key, {});
          const skuMap = map.get(row.sku_key);
          skuMap[row.size] = (skuMap[row.size] || 0) + (row.stock || 0);
        });
        return map;
      }, [poData]);

      const masterSizes = useMemo(() => {
        const sizeSet = new Set();
        (poData.size_level || []).forEach(row => {
          if (row.size) sizeSet.add(row.size);
        });
        const ordered = SIZE_ORDER.filter(s => sizeSet.has(s));
        const extras = Array.from(sizeSet).filter(s => SIZE_RANK[s] === undefined).sort();
        return [...ordered, ...extras];
      }, [poData]);

      const filtered = useMemo(() => {
        let items = poData.sku_level || [];

        if (search) {
          const q = search.toLowerCase();
          items = items.filter(s =>
            s.sku_key.toLowerCase().includes(q) ||
            s.sku_name.toLowerCase().includes(q)
          );
        }

        if (lockSort && lockedSkuOrder && lockedSkuOrder.length > 0) {
          const orderIndex = new Map(lockedSkuOrder.map((k, i) => [k, i]));
          items = [...items].sort((a, b) => {
            const aIdx = orderIndex.get(a.sku_key);
            const bIdx = orderIndex.get(b.sku_key);
            if (aIdx == null && bIdx == null) return 0;
            if (aIdx == null) return 1;
            if (bIdx == null) return -1;
            return aIdx - bIdx;
          });
        } else if (sortConfig.key) {
          items = [...items].sort((a, b) => {
            const aVal = a[sortConfig.key];
            const bVal = b[sortConfig.key];
            if (aVal < bVal) return sortConfig.dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.dir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        return items;
      }, [poData, search, sortConfig, lockSort, lockedSkuOrder]);

      const handleSort = (key) => {
        onSort({
          key,
          dir: sortConfig.key === key && sortConfig.dir === 'asc' ? 'desc' : 'asc'
        });
      };

      const SortHeader = ({ field, children, title }) => (
        <th onClick={() => handleSort(field)} title={title}>
          {children} {sortConfig.key === field ? (sortConfig.dir === 'asc' ? '▲' : '▼') : ''}
        </th>
      );

      return (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <SortHeader field="sku_name" title="SKU Name">SKU</SortHeader>
                <SortHeader field="d_sku" title="Daily demand">D/day</SortHeader>
                <SortHeader field="base_cost_cny" title="Base cost (CNY)">Base CNY</SortHeader>
                <SortHeader field="weight_per_unit_kg" title="Weight per unit">Wt/Unit</SortHeader>
                <SortHeader field="unit_cogs" title="Unit COGS (KZT)">Unit COGS</SortHeader>
                <SortHeader field="avg_sell_price" title="Avg sell price">Avg Price</SortHeader>
                <SortHeader field="net_revenue_unit" title="Net revenue/unit">Net Rev</SortHeader>
                <SortHeader field="profit_unit" title="Profit per unit">Profit</SortHeader>
                <SortHeader field="po_qty_total" title="Order quantity">Order Qty</SortHeader>
                <SortHeader field="po_base_cost_cny" title="PO base cost (CNY)">PO Base CNY</SortHeader>
                <SortHeader field="po_base_cost_kzt" title="PO base cost (KZT)">PO Base KZT</SortHeader>
                <SortHeader field="po_dlv_usd" title="PO delivery (USD)">PO Dlv $</SortHeader>
                <SortHeader field="po_dlv_kzt" title="PO delivery (KZT)">PO Dlv KZT</SortHeader>
                <SortHeader field="po_cogs_kzt" title="PO COGS (KZT)">PO COGS</SortHeader>
                <SortHeader field="monthly_profit" title="Monthly profit">Mon Profit</SortHeader>
                <SortHeader field="k_avg" title="Avg invested capital">K_avg</SortHeader>
                <SortHeader field="roic_pct" title="ROIC %">ROIC</SortHeader>
                <SortHeader field="profit_margin_pct" title="Margin %">Margin</SortHeader>
                {masterSizes.map(size => (
                  <th key={size}>{size}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => {
                const rowClass = row.roic_pct < 10 ? 'low-roic' : row.po_qty_total > 0 ? 'has-order' : '';
                return (
                  <tr key={row.sku_key} className={rowClass}>
                    <td>
                      <strong>{row.sku_name}</strong><br/>
                      <small style={{color:'#9ca3af'}}>{row.sku_key}</small>
                    </td>
                    <td>{row.d_sku?.toFixed(2) || '-'}</td>
                    <td>¥{row.base_cost_cny?.toFixed(0) || '-'}</td>
                    <td>{row.weight_per_unit_kg?.toFixed(2) || '-'}</td>
                    <td>₸{row.unit_cogs?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>₸{row.avg_sell_price?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>₸{row.net_revenue_unit?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td style={{color: (row.profit_unit || 0) > 0 ? '#059669' : '#dc2626'}}>
                      ₸{row.profit_unit?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}
                    </td>
                    <td><strong>{row.po_qty_total}</strong></td>
                    <td>¥{row.po_base_cost_cny?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>₸{row.po_base_cost_kzt?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>${row.po_dlv_usd?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>₸{row.po_dlv_kzt?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>₸{row.po_cogs_kzt?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>{row.monthly_profit?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td>{row.k_avg?.toLocaleString(undefined, {maximumFractionDigits: 0}) || '-'}</td>
                    <td><ROICBadge roic={row.roic_pct} /></td>
                    <td>{row.profit_margin_pct?.toFixed(1) || '-'}%</td>
                    {masterSizes.map(size => {
                      const skuMap = sizeStockMap.get(row.sku_key) || {};
                      const val = skuMap[size] ?? 0;
                      return (
                        <td key={size}>{val}</td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div style={{padding: '40px', textAlign: 'center', color: '#9ca3af'}}>
              No SKUs match the current filters
            </div>
          )}
        </div>
      );
    }

    function App() {
      // Get PO names from data
      const allPOs = DATA.pos || {};
      const poNamesAll = Object.keys(allPOs).sort();
      const poNames = (DATA.active_pos || poNamesAll).slice();
      const archivedPos = (DATA.archived_pos || []).slice();
      const [activePO, setActivePO] = useState(poNames[0] || poNamesAll[0] || 'PO-4');
      const [activeTab, setActiveTab] = useState('sku');
      const [search, setSearch] = useState('');
      const [filterMode, setFilterMode] = useState('all');
      const [skuSort, setSkuSort] = useState({ key: 'po_qty_total', dir: 'desc' });
      const [sizeSort, setSizeSort] = useState({ key: 'sku_key', dir: 'asc' });
      const [horizSort, setHorizSort] = useState({ key: 'po_qty_total', dir: 'desc' });
      const [masterSort, setMasterSort] = useState({ key: 'roic_pct', dir: 'desc' });
      const [lockSort, setLockSort] = useState(false);
      const [lockedSkuOrder, setLockedSkuOrder] = useState([]);

      // FX rates state (editable, persisted in localStorage)
      const defaultFxRates = DATA.fx_rates || { cny_kzt: 78.0, usd_kzt: 530.0 };
      const [fxRates, setFxRates] = useState(() => loadFromStorage('po_fx_rates', defaultFxRates));

      // Multipliers state (per SKU, persisted in localStorage)
      const [multipliers, setMultipliers] = useState(() => loadFromStorage('po_multipliers', {}));

      // Approved state (per PO, per SKU, persisted in localStorage)
      // Structure: { 'PO-4': { 'SKU_KEY': true/false }, ... }
      // Default: all SKUs with po_qty_total > 0 are approved (true)
      const [approvedSkus, setApprovedSkus] = useState(() => loadFromStorage('po_approved_skus', {}));

      // Handler to toggle approval
      const handleApprovalChange = useCallback((poName, skuKey, approved) => {
        setApprovedSkus(prev => {
          const poApprovals = prev[poName] || {};
          return {
            ...prev,
            [poName]: {
              ...poApprovals,
              [skuKey]: approved
            }
          };
        });
      }, []);

      // Helper to check if a SKU is approved (defaults to true if not explicitly set)
      const isApproved = useCallback((poName, skuKey) => {
        const poApprovals = approvedSkus[poName] || {};
        return poApprovals[skuKey] !== false; // Default to true
      }, [approvedSkus]);

      // Persist FX rates on change
      useEffect(() => {
        saveToStorage('po_fx_rates', fxRates);
      }, [fxRates]);

      // Persist multipliers on change
      useEffect(() => {
        saveToStorage('po_multipliers', multipliers);
      }, [multipliers]);

      // Persist approved SKUs on change
      useEffect(() => {
        saveToStorage('po_approved_skus', approvedSkus);
      }, [approvedSkus]);

      const handleFxChange = (key, value) => {
        const numVal = parseFloat(value) || 0;
        setFxRates(prev => ({ ...prev, [key]: numVal }));
      };

      const handleMultiplierChange = (skuKey, value) => {
        const numVal = parseFloat(value) || 1;
        setMultipliers(prev => ({ ...prev, [skuKey]: numVal }));
      };

      const computeSkuOrder = useCallback((poData) => {
        let items = poData?.sku_level || [];

        if (filterMode === 'need_po') items = items.filter(s => s.po_qty_total > 0);
        else if (filterMode === 'zero') items = items.filter(s => s.po_qty_total === 0);

        if (search) {
          const q = search.toLowerCase();
          items = items.filter(s =>
            s.sku_key.toLowerCase().includes(q) ||
            s.sku_name.toLowerCase().includes(q) ||
            (s.notes && s.notes.toLowerCase().includes(q))
          );
        }

        if (skuSort.key) {
          items = [...items].sort((a, b) => {
            let aVal = a[skuSort.key];
            let bVal = b[skuSort.key];
            if (aVal == null) aVal = skuSort.key.includes('date') ? '9999-99-99' : -Infinity;
            if (bVal == null) bVal = skuSort.key.includes('date') ? '9999-99-99' : -Infinity;
            if (aVal < bVal) return skuSort.dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return skuSort.dir === 'asc' ? 1 : -1;
            return 0;
          });
        }
        return items.map(s => s.sku_key);
      }, [filterMode, search, skuSort]);

      const handleLockSortToggle = () => {
        if (!lockSort) {
          const basePo = allPOs['PO-4'] || rawPoData;
          setLockedSkuOrder(computeSkuOrder(basePo));
        } else {
          setLockedSkuOrder([]);
        }
        setLockSort(!lockSort);
      };

      const rawPoData = allPOs[activePO];
      if (!rawPoData) return <div>No PO data found</div>;

      // Constants for recalculation
      const L = rawPoData.lead_time_L || 21;
      const R = rawPoData.reorder_cycle_R || 10;
      const DLV_RATE = 2.66; // USD per kg

      // Recalculate all SKU data based on multipliers and FX rates
      const poData = useMemo(() => {
        const cnyKzt = fxRates.cny_kzt || 78;
        const usdKzt = fxRates.usd_kzt || 530;

        // Helper to add days to date string
        const addDays = (dateStr, days) => {
          const d = new Date(dateStr);
          d.setDate(d.getDate() + days);
          return d.toISOString().split('T')[0];
        };

        // Calculate inbound ADJUSTMENT from previous POs based on approval changes
        // Backend already calculated active_inbound correctly; we only need to track CHANGES
        // When user un-approves a SKU in prior PO, we subtract that from backend's active_inbound
        const inboundAdjustment = {};
        poNamesAll.forEach(pName => {
          // Only look at POs before the active one
          if (pName >= activePO) return;

          const prevPO = allPOs[pName];
          if (!prevPO || !prevPO.sku_level) return;

          const prevApprovals = approvedSkus[pName] || {};

          prevPO.sku_level.forEach(sku => {
            // Check if user explicitly un-approved this SKU (default is approved)
            const wasExplicitlyUnapproved = prevApprovals[sku.sku_key] === false;
            if (wasExplicitlyUnapproved && sku.po_qty_total > 0) {
              // Subtract this from inbound (negative adjustment)
              if (!inboundAdjustment[sku.sku_key]) {
                inboundAdjustment[sku.sku_key] = 0;
              }
              inboundAdjustment[sku.sku_key] -= sku.po_qty_total;
            }
          });
        });

        const isPO4 = rawPoData.po_name === 'PO-4';
        const isPO5 = rawPoData.po_name === 'PO-5';

        // === SHARED PREP DAYS CALCULATION ===
        // Business rule: Each supplier ships only when ALL their approved items are prepared
        // CL items: shared Total_Prep_Clothes = ceil(1.3 * total_CL_weight / 100)
        // ELS items: always prep_days = 1
        const approvedCL = (rawPoData.sku_level || []).filter(s =>
          s.po_qty_total > 0 &&
          isApproved(activePO, s.sku_key) &&
          s.sku_key.startsWith('CL_')
        );
        const totalClWeight = approvedCL.reduce((sum, s) => sum + (s.po_weight_kg || 0), 0);
        const prepOverride = isPO5 ? (rawPoData.prep_days_clothes || rawPoData.summary?.prep_days_clothes) : null;
        const sharedClothesPrep = (Number.isFinite(prepOverride) && prepOverride > 0)
          ? prepOverride
          : (totalClWeight > 0 ? Math.ceil(1.3 * totalClWeight / 100) : 0);
        const sharedElsPrep = 1; // ELS always 1

        // Recalculate SKU-level data
        const recalcSkuLevel = (rawPoData.sku_level || []).map(sku => {
          const mult = multipliers[sku.sku_key] || 1.0;
          const d_adjusted = (sku.d_sku || 0) * mult;

          // Recalculate unit_cogs with new FX rates
          const unit_cogs = (sku.base_cost_cny || 0) * cnyKzt + (sku.weight_per_unit_kg || 0) * DLV_RATE * usdKzt;

          // Target = d_adjusted * t_post_days (PO-4 uses backend target)
          const target = isPO4 ? (sku.target || 0) : d_adjusted * (sku.t_post_days || R);

          // Pre-arrival calculation:
          // For PO-4 (base): use backend's pre_arrival directly (adjusted for demand multiplier)
          // For PO-5+: use backend's pre_arrival + inbound adjustment from user un-approvals
          // effective_L = L + shared_prep_days (shared per supplier type)
          const sku_prep = isPO4
            ? (sku.prep_days || (sku.sku_key.startsWith('CL_') ? sharedClothesPrep : sharedElsPrep))
            : (sku.sku_key.startsWith('CL_') ? sharedClothesPrep :
               sku.sku_key.startsWith('ELS_') ? sharedElsPrep : 3); // fallback
          const effective_L = L + sku_prep;
          const consumption = d_adjusted * effective_L;

          // Use backend's pre_arrival as base, then apply adjustments
          // Backend pre_arrival = stock_at_msg + active_inbound - consumption_msg_to_arr
          // If multiplier changed, we need to recalculate from scratch
          // If only approvals changed, we adjust backend's value
          const inbound_adj = isPO4 ? 0 : (inboundAdjustment[sku.sku_key] || 0);
          let pre_arrival;
          if (isPO4) {
            pre_arrival = sku.pre_arrival || 0;
          } else if (mult === 1.0) {
            // No demand change: use backend's pre_arrival, adjust for unapprovals
            pre_arrival = Math.max(0, (sku.pre_arrival || 0) + inbound_adj);
          } else {
            // Demand changed: recalculate from scratch using backend's stock_at_msg logic
            // Backend: stock_at_msg = stock + inbound + arrivals_before_msg - consumption_to_msg
            // We approximate: use (stock + inbound + active_inbound) adjusted for consumption
            const backend_active_inbound = sku.active_inbound || 0;
            const adjusted_inbound = backend_active_inbound + inbound_adj;
            pre_arrival = Math.max(0, (sku.stock || 0) + (sku.inbound || 0) + adjusted_inbound - consumption);
          }

          // Order qty = max(0, target - pre_arrival)
          const order_qty = isPO4 ? (sku.po_qty_total || 0) : Math.max(0, Math.round(target - pre_arrival));

          // Weight and prep days
          // Use SHARED prep_days per supplier type (not per-SKU weight!)
          // Business rule: Supplier ships when ALL their items are prepared
          const weight_per_unit = sku.weight_per_unit_kg || 0.5;
          const po_weight = order_qty * weight_per_unit;
          const prep_days = isPO4
            ? (sku.prep_days || (sku.sku_key.startsWith('CL_') ? sharedClothesPrep : sharedElsPrep))
            : (sku.sku_key.startsWith('CL_') ? sharedClothesPrep :
               sku.sku_key.startsWith('ELS_') ? sharedElsPrep :
               Math.max(1, Math.ceil(1.3 * po_weight / 100))); // fallback for unknown

          // Dates: Send = Msg + Prep, Arrival = Send + L
          const po_message_date = sku.po_message_date || getTodayDate();
          const po_send_date = addDays(po_message_date, prep_days);
          const est_arr_date = addDays(po_send_date, L);

          // Days of coverage
          const pre_arr_doc = d_adjusted > 0 ? pre_arrival / d_adjusted : (pre_arrival > 0 ? 999 : 0);
          const post_arr_doc = d_adjusted > 0 ? (pre_arrival + order_qty) / d_adjusted : ((pre_arrival + order_qty) > 0 ? 999 : 0);

          // PO costs with new FX rates
          const po_base_cost_cny = order_qty * (sku.base_cost_cny || 0);
          const po_base_cost_kzt = po_base_cost_cny * cnyKzt;
          const po_dlv_usd = order_qty * weight_per_unit * DLV_RATE;
          const po_dlv_kzt = po_dlv_usd * usdKzt;
          const po_cogs_kzt = order_qty * unit_cogs;

          // Unit profit with new COGS
          const net_revenue = sku.net_revenue_unit || 0;
          const profit_unit = net_revenue - unit_cogs;

          // Recalculate ROIC and economics
          const monthly_profit = profit_unit * d_adjusted * 30;
          const ss_ratio = (sku.t_post_days || R) - R; // SS/D approximation
          const ss_total = d_adjusted * ss_ratio;
          const k_avg = d_adjusted * (L + R/2) * unit_cogs + ss_total * unit_cogs;
          const roic_pct = k_avg > 0 ? (monthly_profit / k_avg) * 100 : 0;
          const profit_margin_pct = unit_cogs > 0 ? (profit_unit / unit_cogs) * 100 : 0;

          // Recalculate size_orders based on multiplier
          const size_orders = {};
          if (isPO4 && sku.size_orders) {
            Object.entries(sku.size_orders).forEach(([size, origQty]) => {
              size_orders[size] = origQty;
            });
          } else if (sku.size_orders) {
            const totalOriginal = Object.values(sku.size_orders).reduce((a, b) => a + b, 0);
            if (totalOriginal > 0 && order_qty > 0) {
              Object.entries(sku.size_orders).forEach(([size, origQty]) => {
                const ratio = origQty / totalOriginal;
                size_orders[size] = Math.round(order_qty * ratio);
              });
              // Adjust to match total
              const newTotal = Object.values(size_orders).reduce((a, b) => a + b, 0);
              if (newTotal !== order_qty && Object.keys(size_orders).length > 0) {
                const firstSize = Object.keys(size_orders)[0];
                size_orders[firstSize] += (order_qty - newTotal);
              }
            }
          }

          return {
            ...sku,
            d_sku_adjusted: d_adjusted,
            target: Math.round(target),
            consumption_until_arrival: Math.round(consumption * 10) / 10,
            pre_arrival: Math.round(pre_arrival),
            active_inbound: (sku.active_inbound || 0) + inbound_adj, // Backend value adjusted for unapprovals
            po_qty_total: order_qty,
            po_weight_kg: Math.round(po_weight * 100) / 100,
            prep_days,
            po_send_date,
            est_arr_date,
            days_until_arrival: prep_days + L,
            pre_arr_doc: Math.round(pre_arr_doc * 10) / 10,
            post_arr_doc: Math.round(post_arr_doc * 10) / 10,
            unit_cogs: Math.round(unit_cogs),
            profit_unit: Math.round(profit_unit),
            po_base_cost_cny: Math.round(po_base_cost_cny),
            po_base_cost_kzt: Math.round(po_base_cost_kzt),
            po_dlv_usd: Math.round(po_dlv_usd * 100) / 100,
            po_dlv_kzt: Math.round(po_dlv_kzt),
            po_cogs_kzt: Math.round(po_cogs_kzt),
            monthly_profit: Math.round(monthly_profit),
            k_avg: Math.round(k_avg),
            roic_pct: Math.round(roic_pct * 10) / 10,
            profit_margin_pct: Math.round(profit_margin_pct * 10) / 10,
            roic_below_threshold: roic_pct < 15,
            size_orders
          };
        });

        // Recalculate size-level data
        const recalcSizeLevel = (rawPoData.size_level || []).map(size => {
          const skuMult = multipliers[size.sku_key] || 1.0;
          const d_adjusted = (size.d_size || 0) * skuMult;

          // Find parent SKU for weight_per_unit
          const parentSku = recalcSkuLevel.find(s => s.sku_key === size.sku_key);
          const weight_per_unit = parentSku?.weight_per_unit_kg || 0.5;
          const unit_cogs = parentSku?.unit_cogs || size.unit_cogs || 5000;

          if (isPO4) {
            const order_qty = size.order_qty || 0;
            const po_weight = order_qty * weight_per_unit;
            const prep_days = size.prep_days || parentSku?.prep_days || 1;
            const po_send_date = size.po_send_date || parentSku?.po_send_date || rawPoData.po_send_date;
            const est_arr_date = size.est_arr_date || parentSku?.est_arr_date || rawPoData.est_arr_date;
            return {
              ...size,
              d_size_adjusted: d_adjusted,
              order_qty,
              weight_kg: Math.round(po_weight * 100) / 100,
              prep_days,
              po_send_date,
              est_arr_date,
              days_until_arrival: prep_days + L,
              po_cogs_kzt: Math.round(order_qty * unit_cogs)
            };
          }

          const sizeOrderFromSku = parentSku?.size_orders?.[size.size];
          const order_qty = Math.max(0, Math.round(sizeOrderFromSku ?? size.order_qty ?? 0));
          const effective_L = size.days_until_arrival || parentSku?.days_until_arrival || (L + 3);
          const consumption = size.consumption_until_arrival ?? (d_adjusted * effective_L);
          const pre_arrival = size.pre_arrival ?? Math.max(
            0,
            (size.stock || 0) + (size.inbound || 0) + (size.active_inbound || 0) - consumption
          );
          const target = size.target ?? Math.round(d_adjusted * (size.t_post_days || R));

          const po_weight = order_qty * weight_per_unit;
          const prep_days = size.prep_days || parentSku?.prep_days ||
                            (size.sku_key.startsWith('CL_') ? sharedClothesPrep :
                            size.sku_key.startsWith('ELS_') ? sharedElsPrep :
                            Math.max(1, Math.ceil(1.3 * po_weight / 100)));
          const po_message_date = size.po_message_date || parentSku?.po_message_date || getTodayDate();
          const po_send_date = size.po_send_date || parentSku?.po_send_date || addDays(po_message_date, prep_days);
          const est_arr_date = size.est_arr_date || parentSku?.est_arr_date || addDays(po_send_date, L);

          const pre_arr_doc = d_adjusted > 0 ? pre_arrival / d_adjusted : (pre_arrival > 0 ? 999 : 0);
          const post_arr_doc = d_adjusted > 0 ? (pre_arrival + order_qty) / d_adjusted : ((pre_arrival + order_qty) > 0 ? 999 : 0);

          return {
            ...size,
            d_size_adjusted: d_adjusted,
            target: Math.round(target),
            consumption_until_arrival: Math.round(consumption * 10) / 10,
            pre_arrival: Math.round(pre_arrival),
            order_qty,
            weight_kg: Math.round(po_weight * 100) / 100,
            prep_days,
            po_send_date,
            est_arr_date,
            days_until_arrival: prep_days + L,
            pre_arr_doc: Math.round(pre_arr_doc * 10) / 10,
            post_arr_doc: Math.round(post_arr_doc * 10) / 10,
            po_cogs_kzt: Math.round(order_qty * unit_cogs)
          };
        });

        // Recalculate size_horizontal
        const recalcSizeHorizontal = (rawPoData.size_horizontal || []).map(row => {
          const skuData = recalcSkuLevel.find(s => s.sku_key === row.sku_key);
          return {
            ...row,
            d_sku: skuData?.d_sku_adjusted || row.d_sku,
            po_qty_total: skuData?.po_qty_total || 0,
            size_orders: skuData?.size_orders || {}
          };
        });

        // Recalculate summary
        const skusWithOrders = recalcSkuLevel.filter(s => s.po_qty_total > 0);
        const summary = {
          ...rawPoData.summary,
          total_units: recalcSkuLevel.reduce((sum, s) => sum + s.po_qty_total, 0),
          total_weight_kg: Math.round(recalcSkuLevel.reduce((sum, s) => sum + s.po_weight_kg, 0) * 10) / 10,
          skus_with_orders: skusWithOrders.length,
          skus_without_orders: recalcSkuLevel.length - skusWithOrders.length,
          total_po_base_cost_cny: Math.round(skusWithOrders.reduce((sum, s) => sum + s.po_base_cost_cny, 0)),
          total_po_base_cost_kzt: Math.round(skusWithOrders.reduce((sum, s) => sum + s.po_base_cost_kzt, 0)),
          total_po_dlv_usd: Math.round(skusWithOrders.reduce((sum, s) => sum + s.po_dlv_usd, 0) * 100) / 100,
          total_po_dlv_kzt: Math.round(skusWithOrders.reduce((sum, s) => sum + s.po_dlv_kzt, 0)),
          total_po_cogs_kzt: Math.round(skusWithOrders.reduce((sum, s) => sum + s.po_cogs_kzt, 0)),
          avg_prep_days: skusWithOrders.length > 0 ? Math.round(skusWithOrders.reduce((sum, s) => sum + s.prep_days, 0) / skusWithOrders.length) : 5
        };

        // Get representative dates from first SKU with orders
        const firstSkuWithOrder = skusWithOrders[0];
        const po_send_date = firstSkuWithOrder?.po_send_date || rawPoData.po_send_date;
        const est_arr_date = firstSkuWithOrder?.est_arr_date || rawPoData.est_arr_date;

        return {
          ...rawPoData,
          summary,
          sku_level: recalcSkuLevel,
          size_level: recalcSizeLevel,
          size_horizontal: recalcSizeHorizontal,
          po_send_date,
          est_arr_date
        };
      }, [rawPoData, multipliers, fxRates, activePO, approvedSkus, poNamesAll]);

      const skuWithOrders = (poData.sku_level || []).filter(s => s.po_qty_total > 0).length;
      const skuZero = (poData.sku_level || []).filter(s => s.po_qty_total === 0).length;

      return (
        <div className="container">
          <div className="header">
            <div style={{display: 'flex', alignItems: 'center', gap: '24px'}}>
              <h1>PO Dashboard</h1>
              <div className="fx-rates">
                <div className="fx-rate-item">
                  <label>CNY/KZT:</label>
                  <input
                    type="number"
                    className="fx-rate-input"
                    value={fxRates.cny_kzt}
                    onChange={e => handleFxChange('cny_kzt', e.target.value)}
                    step="0.1"
                  />
                </div>
                <div className="fx-rate-item">
                  <label>USD/KZT:</label>
                  <input
                    type="number"
                    className="fx-rate-input"
                    value={fxRates.usd_kzt}
                    onChange={e => handleFxChange('usd_kzt', e.target.value)}
                    step="1"
                  />
                </div>
              </div>
            </div>
            <div style={{display: 'flex', gap: '12px', alignItems: 'center'}}>
              <div className="export-btns">
                <button className="export-btn" onClick={() => exportCurrentPO(poData, activePO, isApproved)}>
                  Export {activePO}
                </button>
                <button className="export-btn primary" onClick={() => exportAllPOs(DATA.pos, isApproved)}>
                  Export All POs
                </button>
              </div>
              <div className="po-selector">
                {poNames.map(po => (
                  <button
                    key={po}
                    className={`po-btn ${activePO === po ? 'active' : ''}`}
                    onClick={() => setActivePO(po)}
                  >
                    {po}
                  </button>
                ))}
              </div>
              {archivedPos.length > 0 && (
                <div className="po-selector" style={{marginTop:'6px'}}>
                  <span style={{fontSize:'12px', color:'#6b7280', marginRight:'6px'}}>Archived:</span>
                  {archivedPos.map(po => (
                    <button
                      key={po}
                      className={`po-btn ${activePO === po ? 'active' : ''}`}
                      onClick={() => setActivePO(po)}
                    >
                      {po}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DateHeaders poData={poData} activePO={activePO} isApproved={isApproved} />
          <CutoffBanner poData={poData} />
          <SummaryCards poData={poData} activePO={activePO} isApproved={isApproved} />
          <TotalsSection poData={poData} fxRates={fxRates} activePO={activePO} isApproved={isApproved} />

          <div className="controls">
            <input
              type="text"
              className="search-input"
              placeholder="Search SKU, name, or notes..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <div style={{display: 'flex', gap: '6px'}}>
              <button
                className={`filter-btn ${filterMode === 'all' ? 'active' : ''}`}
                onClick={() => setFilterMode('all')}
              >
                All ({poData.sku_level?.length || 0})
              </button>
              <button
                className={`filter-btn ${filterMode === 'need_po' ? 'active' : ''}`}
                onClick={() => setFilterMode('need_po')}
              >
                Need PO ({skuWithOrders})
              </button>
              <button
                className={`filter-btn ${filterMode === 'zero' ? 'active' : ''}`}
                onClick={() => setFilterMode('zero')}
              >
                No Order ({skuZero})
              </button>
              <button
                className={`filter-btn ${lockSort ? 'active' : ''}`}
                onClick={handleLockSortToggle}
                title="Lock PO-4 SKU order and reuse across all POs"
              >
                Lock Sort
              </button>
            </div>
          </div>

          <div style={{marginBottom: '0'}}>
            <button
              className={`tab-btn ${activeTab === 'sku' ? 'active' : ''}`}
              onClick={() => setActiveTab('sku')}
            >
              SKU Level ({poData.sku_level?.length || 0})
            </button>
            <button
              className={`tab-btn ${activeTab === 'size' ? 'active' : ''}`}
              onClick={() => setActiveTab('size')}
            >
              Size Level ({poData.size_level?.length || 0})
            </button>
            <button
              className={`tab-btn ${activeTab === 'horiz' ? 'active' : ''}`}
              onClick={() => setActiveTab('horiz')}
            >
              Size-Horizontal ({poData.size_horizontal?.length || 0})
            </button>
            <button
              className={`tab-btn ${activeTab === 'master' ? 'active' : ''}`}
              onClick={() => setActiveTab('master')}
            >
              Master Params
            </button>
          </div>

          {activeTab === 'sku' && (
            <SKUTable
              poData={poData}
              search={search}
              filterMode={filterMode}
              sortConfig={skuSort}
              onSort={setSkuSort}
              multipliers={multipliers}
              onMultiplierChange={handleMultiplierChange}
              activePO={activePO}
              isApproved={isApproved}
              onApprovalChange={handleApprovalChange}
              lockSort={lockSort}
              lockedSkuOrder={lockedSkuOrder}
            />
          )}
          {activeTab === 'size' && (
            <SizeTable
              poData={poData}
              search={search}
              filterMode={filterMode}
              sortConfig={sizeSort}
              onSort={setSizeSort}
              lockSort={lockSort}
              lockedSkuOrder={lockedSkuOrder}
            />
          )}
          {activeTab === 'horiz' && (
            <SizeHorizontalTable
              poData={poData}
              search={search}
              filterMode={filterMode}
              sortConfig={horizSort}
              onSort={setHorizSort}
              lockSort={lockSort}
              lockedSkuOrder={lockedSkuOrder}
            />
          )}
          {activeTab === 'master' && (
            <MasterParamsTable
              poData={poData}
              search={search}
              sortConfig={masterSort}
              onSort={setMasterSort}
              lockSort={lockSort}
              lockedSkuOrder={lockedSkuOrder}
            />
          )}

          <div style={{marginTop: '20px', fontSize: '11px', color: '#9ca3af', textAlign: 'center'}}>
            Generated: {DATA.generated_at} | Base Stock: {DATA.base_stock_date} | Cutoff: {DATA.cutoff_date}
          </div>
        </div>
      );
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  </script>
</body>
</html>
'''


def main():
    print("Generating PO Dashboard HTML...")

    # Load JSON data
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)

    # Embed JSON into HTML template
    json_str = json.dumps(data, indent=2)
    html_content = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)

    # Write output
    with open(OUTPUT_PATH, 'w') as f:
        f.write(html_content)

    # Print summary
    print(f"Generated: {OUTPUT_PATH}")
    print(f"  - POs included: {list(data.get('pos', {}).keys())}")

    for po_name, po_data in data.get('pos', {}).items():
        summary = po_data.get('summary', {})
        print(f"  - {po_name}: {summary.get('skus_with_orders', 0)} SKUs need {summary.get('total_units', 0)} units")


if __name__ == "__main__":
    main()
