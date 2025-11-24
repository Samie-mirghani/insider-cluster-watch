# Politician Time-Decay Maintenance Tools

This directory contains tools for maintaining politician statuses in the time-decay system.

## 📁 Files Overview

| File | Purpose | When to Use |
|------|---------|-------------|
| `update_politician_status.py` | Update politician statuses | Quarterly reviews, retirement announcements |
| `view_politician_status.py` | View current statuses & weights | Quick checks, verification |
| `test_time_decay.py` | Test time-decay calculations | Verify system working correctly |
| `POLITICIAN_MAINTENANCE_GUIDE.md` | Comprehensive maintenance guide | Reference for all procedures |

---

## 🚀 Quick Start

### View Current Status

```bash
cd /home/user/insider-cluster-watch

# View all politicians
python jobs/view_politician_status.py

# View only retiring politicians
python jobs/view_politician_status.py --status retiring

# Sort by weight (highest first)
python jobs/view_politician_status.py --sort weight

# Show detailed information
python jobs/view_politician_status.py --details
```

**Output Example:**
```
====================================================================================================
Name                      Status     Party  Office   Base     Current    Note
====================================================================================================
Brian Higgins             retiring   D      House    1.30x    1.95x      🔥 BOOSTED 1.5x
Dan Crenshaw              active     R      House    1.50x    1.50x      ✅ Active
Nancy Pelosi              retired    D      House    2.00x    0.40x      📉 700d ago
Paul Pelosi               active     D      Spouse   2.00x    2.00x      ✅ Active
====================================================================================================
```

---

### Update Politician Status

```bash
cd /home/user/insider-cluster-watch

# 1. Edit the script
nano jobs/update_politician_status.py
   # Update the UPDATES dictionary with your changes

# 2. Run the update
python jobs/update_politician_status.py

# 3. Review the changes and confirm

# 4. Commit the changes
git add data/politician_registry.json
git commit -m "Update politician statuses - $(date +%Y-%m-%d)"
git push
```

**Example Update:**
```python
UPDATES = {
    'Some Politician': {
        'action': 'set_retiring',
        'term_ended': '2025-01-03',
        'retirement_announced': '2024-11-15',
        'reason': 'Announced retirement'
    },
}
```

---

### Test Time-Decay System

```bash
cd /home/user/insider-cluster-watch
python jobs/test_time_decay.py
```

**This will show:**
- ✅ Current registry statistics
- ✅ Weight calculations by status
- ✅ Time-decay demonstration
- ✅ All current weights
- ✅ Lame duck pattern analysis

---

## 📋 Common Tasks

### Task 1: Politician Announces Retirement

**Scenario:** Brian Higgins announced retirement

**Steps:**
1. Edit `jobs/update_politician_status.py`:
   ```python
   UPDATES = {
       'Brian Higgins': {
           'action': 'set_retiring',
           'term_ended': '2025-02-01',
           'retirement_announced': '2024-11-08',
           'reason': 'Announced early retirement'
       },
   }
   ```

2. Run: `python jobs/update_politician_status.py`

3. **Result:** Weight boosted from 1.3x → 1.95x (1.5x boost!)

---

### Task 2: Politician Leaves Office

**Scenario:** Politician's term ended

**Steps:**
1. Edit `jobs/update_politician_status.py`:
   ```python
   UPDATES = {
       'Nancy Pelosi': {
           'action': 'set_retired',
           'term_ended': '2023-01-03',
           'reason': 'Left Speaker position'
       },
   }
   ```

2. Run: `python jobs/update_politician_status.py`

3. **Result:** Time-decay begins (90-day half-life)

---

### Task 3: Add New Politician

**Scenario:** Found new high-volume trader on Capitol Trades

**Steps:**
1. Check their trading history on Capitol Trades
2. Determine base weight (1.0-2.0x based on performance)
3. Edit `jobs/update_politician_status.py`:
   ```python
   UPDATES = {
       'New Politician Name': {
           'action': 'add_new',
           'party': 'D',
           'office': 'House',
           'state': 'CA',
           'district': '12',
           'base_weight': 1.2,
           'reason': 'High trading volume, consistent activity'
       },
   }
   ```

4. Run: `python jobs/update_politician_status.py`

---

### Task 4: Quarterly Review

**Recommended: January, April, July, October**

```bash
# 1. Check current status
python jobs/view_politician_status.py --sort weight

# 2. Review sources
#    - congress.gov/members
#    - Recent news for retirements
#    - Capitol Trades for new traders

# 3. Check for changes
#    - Any retirements announced?
#    - Any politicians left office?
#    - Any new high-volume traders?

# 4. If changes needed, run update script
python jobs/update_politician_status.py

# 5. Verify with test script
python jobs/test_time_decay.py

# 6. Commit changes
git add data/politician_registry.json
git commit -m "Quarterly politician status update - Q4 2024"
git push
```

---

## 🎯 Status Types & Effects

### Active (✅)
- **Weight:** Full base weight (e.g., 2.0x stays 2.0x)
- **When:** Politician currently in office
- **Action:** None needed until retirement announced

### Retiring (🔥)
- **Weight:** BOOSTED by 1.5x (e.g., 1.3x → 1.95x)
- **When:** Retirement announced but not yet effective
- **Why:** "Lame duck" trades can be highly informative!
- **Action:** Update when retirement announced

### Retired (📉)
- **Weight:** Exponential decay (half-life: 90 days)
  - Day 0: 100% of base weight
  - Day 90: 50%
  - Day 180: 25%
  - Day 270+: 20% (floor)
- **When:** Politician has left office
- **Why:** Historical value preserved, never deleted
- **Action:** Update when term ends

---

## 📊 Weight Guidelines

When adding new politicians, use these guidelines for base weight:

| Performance Level | Base Weight | Criteria |
|------------------|-------------|----------|
| **Legendary** | 2.0x | Exceptional track record, high-profile (e.g., Nancy/Paul Pelosi) |
| **Excellent** | 1.5-1.8x | Strong performance, frequent successful trades |
| **Good** | 1.2-1.4x | Above-average returns, consistent activity |
| **Average** | 1.0x | Default for new additions, unproven track record |

**How to determine:**
1. Review trading history on Capitol Trades (last 6-12 months)
2. Check trade frequency (monthly average)
3. Review position sizes ($100k+ trades more significant)
4. Look for successful patterns
5. Compare to existing tracked politicians

---

## 🔍 Information Sources

### Official Sources
- **Congress.gov** - https://www.congress.gov/members
- **House.gov** - https://www.house.gov/representatives
- **Senate.gov** - https://www.senate.gov/senators

### Trading Activity
- **Capitol Trades** - https://www.capitoltrades.com
- **Quiver Quantitative** - https://www.quiverquant.com/congresstrading

### News & Analysis
- **Politico** - https://www.politico.com
- **The Hill** - https://thehill.com
- **Roll Call** - https://rollcall.com

---

## 🚨 Important Notes

### DO:
✅ Update status when retirement **announced** (captures lame duck boost!)
✅ Verify dates from official sources
✅ Commit changes to git
✅ Run quarterly reviews
✅ Check Capitol Trades for new traders

### DON'T:
❌ Delete politicians from registry (time-decay preserves data!)
❌ Forget to update `term_ended` dates
❌ Skip quarterly reviews
❌ Add politicians without trade history
❌ Use unverified sources

---

## 📞 Support

- **Full Maintenance Guide:** See `POLITICIAN_MAINTENANCE_GUIDE.md`
- **Code Documentation:** See `jobs/politician_tracker.py`
- **Configuration:** See `jobs/config.py` (lines 109-128)

---

## 🔄 File Locations

```
insider-cluster-watch/
├── data/
│   └── politician_registry.json          # Politician metadata (5.3 KB)
│
├── jobs/
│   ├── politician_tracker.py             # Core tracker module
│   ├── update_politician_status.py       # Update script
│   ├── view_politician_status.py         # View/query tool
│   ├── test_time_decay.py                # Test suite
│   └── config.py                         # Configuration (lines 109-128)
│
└── docs/
    ├── POLITICIAN_MAINTENANCE_GUIDE.md   # Comprehensive guide
    └── POLITICIAN_TOOLS_README.md        # This file
```

---

**Last Updated:** 2024-11-24
**Maintainer:** See `POLITICIAN_MAINTENANCE_GUIDE.md` for maintenance procedures
