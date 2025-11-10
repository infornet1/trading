# Dashboard Filter Feature - Win/Loss Only

## ✅ Feature Added

The dashboard now filters signals to show **only completed signals (Win/Loss) by default**, hiding pending signals that haven't reached target or stop loss yet.

## 🎯 What This Solves

**Before:**
- Dashboard showed ALL signals including pending ones
- Pending signals diluted the actual win rate
- Hard to see real performance at a glance

**After:**
- Shows only completed signals by default (WIN, LOSS, TIMEOUT)
- Clear view of actual trading performance
- Can still switch to see all or pending signals

## 🔘 Filter Buttons

Three filter options above the signals table:

1. **Win/Loss Only** (Default) ✅
   - Shows: WIN, LOSS, TIMEOUT
   - Hides: PENDING signals
   - Best for: Seeing actual performance

2. **Show All**
   - Shows: All signals including pending
   - Best for: Complete overview

3. **Pending Only**
   - Shows: Only PENDING signals
   - Hides: Completed signals
   - Best for: Monitoring active signals

## 📊 Signal Counter Badge

Added a live counter next to "Recent Signals" heading:
- Shows number of signals currently displayed
- Updates when you change filters
- Example: "Recent Signals **12**" (showing 12 signals)

## 🎨 Visual Design

**Filter Buttons:**
- Located in top-right of signals table
- Active button highlighted in green
- Matches existing time selector style
- Responsive layout

**Counter Badge:**
- Green pill-shaped badge
- Shows current signal count
- Updates in real-time

## 🔍 How It Works

### Default Behavior (Page Load)
```
1. Dashboard loads
2. Fetches last 50 signals
3. Automatically filters to show only WIN/LOSS/TIMEOUT
4. Updates counter (e.g., "12" out of 50 total)
5. Displays filtered results
```

### Switching Filters
```
1. Click "Show All"
2. JavaScript filters the existing data
3. No new API call needed (instant)
4. Counter updates to show total
5. Table refreshes with all signals
```

### Filter Logic
```javascript
'completed': Shows WIN, LOSS, TIMEOUT only
'all': Shows everything (no filter)
'pending': Shows PENDING or null only
```

## 📋 Example Scenarios

### Scenario 1: Fresh Start
```
Total signals: 0
Filter: Win/Loss Only (default)
Display: "No completed signals yet. Signals need time to reach target or stop loss."
Counter: 0
```

### Scenario 2: Mix of Signals
```
Total signals: 45
├── Completed: 28 (18 WIN, 9 LOSS, 1 TIMEOUT)
└── Pending: 17

Filter: Win/Loss Only (default)
Display: 28 signals shown
Counter: 28

Click "Show All":
Display: 45 signals shown
Counter: 45

Click "Pending Only":
Display: 17 signals shown
Counter: 17
```

### Scenario 3: All Resolved
```
Total signals: 50
├── Completed: 50 (32 WIN, 18 LOSS)
└── Pending: 0

Filter: Win/Loss Only (default)
Display: 50 signals shown
Counter: 50

Click "Pending Only":
Display: "No pending signals. All signals have been resolved."
Counter: 0
```

## 💡 Benefits

### 1. **Clearer Win Rate**
- Only shows resolved signals
- Win rate more accurate
- Not diluted by pending trades

### 2. **Better Decision Making**
- See actual performance immediately
- Identify winning vs losing setups
- Track real results, not theoretical

### 3. **Flexibility**
- Switch to see all signals anytime
- Monitor pending signals separately
- Choose view based on need

### 4. **Real-Time Feedback**
- Counter updates instantly
- No page reload needed
- Smooth user experience

## 🧪 Testing the Feature

### Test 1: Default Filter
```
1. Open dashboard: http://localhost:5800
2. Check signals table header
3. Should see "Win/Loss Only" button active (green)
4. Only WIN/LOSS/TIMEOUT signals displayed
5. Counter shows correct number
```

### Test 2: Switch Filters
```
1. Click "Show All"
2. Button becomes active
3. More signals appear (including pending)
4. Counter increases

2. Click "Pending Only"
3. Only PENDING signals shown
4. Counter shows pending count

3. Click "Win/Loss Only"
4. Back to completed signals only
```

### Test 3: Auto-Refresh
```
1. Let dashboard auto-refresh (30 seconds)
2. Filter selection persists
3. Counter updates with new data
4. Still shows only selected filter type
```

### Test 4: Manual Refresh
```
1. Select "Win/Loss Only"
2. Click "🔄 Refresh Now" button
3. Filter remains on "Win/Loss Only"
4. Data refreshes but filter stays
```

## 🎯 Use Cases

### Use Case 1: Daily Performance Check
```
Goal: See how today's signals performed

Steps:
1. Open dashboard
2. Select "Last 24 Hours" time period
3. Already filtered to "Win/Loss Only"
4. View win rate and results
5. Ignore pending signals (not complete yet)
```

### Use Case 2: Monitor Active Trades
```
Goal: Check signals currently running

Steps:
1. Open dashboard
2. Click "Pending Only" filter
3. See signals waiting to hit target/stop
4. Check how long they've been pending
5. Decide if you want to manually intervene
```

### Use Case 3: Complete Analysis
```
Goal: Analyze all signals for patterns

Steps:
1. Open dashboard
2. Click "Show All" filter
3. See complete picture
4. Export data if needed
5. Look for patterns in all signal types
```

## 📝 Technical Details

### JavaScript Variables
```javascript
let currentFilter = 'completed';  // Default filter state
let allSignals = [];              // Store all fetched signals
```

### Filter Function
```javascript
function filterSignalsByType(signals, filterType) {
    if (filterType === 'completed') {
        return signals.filter(sig =>
            sig.final_result &&
            ['WIN', 'LOSS', 'TIMEOUT'].includes(sig.final_result)
        );
    } else if (filterType === 'pending') {
        return signals.filter(sig =>
            !sig.final_result || sig.final_result === 'PENDING'
        );
    } else {
        return signals;  // 'all'
    }
}
```

### Button Handler
```javascript
function filterSignals(filterType, clickedButton) {
    currentFilter = filterType;
    // Update active button
    // Apply filter
    // Redisplay table
}
```

## 🔄 State Persistence

**Filter persists:**
- ✅ During auto-refresh (every 30 seconds)
- ✅ During manual refresh (🔄 button)
- ✅ When switching time periods

**Filter resets:**
- ❌ On page reload (back to default "Win/Loss Only")
- ❌ This is intentional - default is most useful

## 🎨 Customization

### Change Default Filter

Edit `templates/dashboard.html` line ~288:
```javascript
// Change this line:
let currentFilter = 'completed';  // Default

// To:
let currentFilter = 'all';  // Show all by default
// or
let currentFilter = 'pending';  // Show pending by default
```

### Change Button Labels

Edit button text in HTML (~268-270):
```html
<button onclick="filterSignals('completed', this)">Resolved ✅</button>
<button onclick="filterSignals('all', this)">Everything 📊</button>
<button onclick="filterSignals('pending', this)">Active ⏳</button>
```

### Add More Filter Types

Could add filters for:
- Wins only: `sig.final_result === 'WIN'`
- Losses only: `sig.final_result === 'LOSS'`
- By signal type: `sig.signal_type === 'RSI_OVERSOLD'`
- By direction: `sig.direction === 'LONG'`

## ✅ Summary

**Feature:** Signal filtering in dashboard
**Default:** Win/Loss Only (completed signals)
**Options:** Win/Loss Only, Show All, Pending Only
**Benefit:** Clearer view of actual performance
**Location:** Above signals table, right side
**Counter:** Shows number of filtered signals

**Perfect for:** Quickly seeing real trading results without pending signals cluttering the view!

---

**The dashboard now defaults to showing only completed signals, making it much easier to evaluate actual strategy performance!** 🎉
