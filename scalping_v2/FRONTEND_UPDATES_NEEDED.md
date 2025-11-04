# Frontend Updates for Dashboard Improvements

## Changes Needed

### 1. Update dashboard.html (Line 32-36)

Replace:
```html
<div class="stat-card">
    <div class="stat-label">Total P&L</div>
    <div class="stat-value" id="totalPnl">$0.00</div>
    <div class="stat-change" id="pnlPercent">+0.00%</div>
</div>
```

With:
```html
<div class="stat-card">
    <div class="stat-label">Gross P&L</div>
    <div class="stat-value" id="totalPnl">$0.00</div>
    <div class="stat-change" id="pnlPercent">+0.00%</div>
</div>
<div class="stat-card highlight">
    <div class="stat-label">Net P&L (After Fees)</div>
    <div class="stat-value" id="netPnl">$0.00</div>
    <div class="stat-change">Fees: <span id="totalFees">$0.00</span> (<span id="totalTrades">0</span> trades)</div>
</div>
```

### 2. Update dashboard.js (After line 87)

Add this code after the unrealizedPnl update:
```javascript
// Update Net P&L After Fees (NEW)
if (account.net_pnl !== undefined) {
    document.getElementById('netPnl').textContent = formatCurrency(account.net_pnl);
    document.getElementById('totalFees').textContent = formatCurrency(account.estimated_fees);
    document.getElementById('totalTrades').textContent = account.total_trades || 0;
    setColorClass('netPnl', account.net_pnl);
}

// Update Active Filters Status (NEW)
if (data.active_filters) {
    const filters = data.active_filters;
    console.log('Active Filters:', filters);
    // Store for potential dashboard display
    window.activeFilters = filters;
}
```

### 3. Add CSS for highlight class (dashboard.css)

```css
.stat-card.highlight {
    border: 2px solid #00d4aa;
    background: linear-gradient(135deg, #0a1929 0%, #0d2b3e 100%);
}

.stat-card.highlight .stat-label {
    color: #00d4aa;
    font-weight: 600;
}
```

## Backend Status

✅ `/api/status` endpoint updated with:
- `net_pnl`
- `estimated_fees`
- `total_trades`
- `net_return_percent`
- `active_filters`

✅ `live_trader.py` exports `active_filters` in snapshot

✅ Database indexes created for performance

## Testing

After implementing frontend changes:
1. Restart dashboard: `sudo systemctl restart scalping-dashboard`
2. Hard refresh browser (Ctrl+Shift+R)
3. Check console for filter data
4. Verify Net P&L displays correctly

## API Response Example

```json
{
  "account": {
    "balance": 1034.56,
    "total_pnl": 34.56,
    "net_pnl": 28.56,
    "estimated_fees": 6.00,
    "total_trades": 6
  },
  "active_filters": {
    "signal_cooldown_active": true,
    "cooldown_seconds": 120,
    "choppy_blocker_active": true,
    "time_filter_active": true,
    "min_confidence": 70.0
  }
}
```
