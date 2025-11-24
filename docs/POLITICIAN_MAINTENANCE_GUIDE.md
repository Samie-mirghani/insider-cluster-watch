# Politician Status Maintenance Guide

**Last Updated:** 2024-11-24
**Maintenance Schedule:** Quarterly + As-Needed

---

## 📅 Maintenance Schedule

### Quarterly Reviews (Recommended)
- **January:** Post-election updates, new Congress begins
- **April:** Mid-quarter check for unexpected resignations
- **July:** Pre-election season review
- **October:** Pre-election updates, retirement announcements

### As-Needed Updates
- **When retirement announced:** Immediate update to capture "lame duck" urgency boost
- **When politician leaves office:** Update within 1 week of departure
- **After elections:** Within 1 month of new Congress convening

---

## 🔍 Where to Find Information

### Official Sources
1. **Congress.gov** (https://www.congress.gov/members)
   - Official member directory
   - Current status, districts, terms
   - Most authoritative source

2. **House.gov** (https://www.house.gov/representatives)
   - Current House members
   - District maps and contact info

3. **Senate.gov** (https://www.senate.gov/senators/)
   - Current Senators
   - Term expiration dates

### News & Tracking
4. **Capitol Trades** (https://www.capitoltrades.com)
   - Recent trading activity
   - Identify new high-volume traders to add

5. **Ballotpedia**
   - Election results
   - Retirement announcements
   - Congressional changes

6. **Major News Outlets**
   - Politico, The Hill, Roll Call
   - Retirement announcements
   - Resignations and special elections

---

## 🛠️ How to Update Politician Statuses

### Step 1: Gather Information

Create a checklist of changes:

```
□ Check congress.gov for current members
□ Review news for retirement announcements (last 3 months)
□ Check Capitol Trades for new high-volume traders
□ Verify any politicians marked as "retiring" have left office
□ Note any politicians returning to office (rare)
```

### Step 2: Edit Update Script

Open `jobs/update_politician_status.py` and update the `UPDATES` dictionary:

```python
UPDATES = {
    'Politician Name': {
        'action': 'set_retiring',  # or 'set_retired', 'add_new', 'set_active'
        'term_ended': '2025-01-03',
        'retirement_announced': '2024-11-15',
        'reason': 'Brief description of why'
    },
}
```

### Step 3: Run Update Script

```bash
cd /home/user/insider-cluster-watch
python jobs/update_politician_status.py
```

The script will:
- ✅ Show current registry stats
- ✅ Process each update
- ✅ Display weight changes
- ✅ Save updated registry
- ✅ Show next steps

### Step 4: Review Changes

Check the output:
- ✅ All updates successful?
- ✅ Weight changes look correct?
- ✅ Status transitions make sense?

### Step 5: Commit Changes

```bash
git add data/politician_registry.json
git commit -m "Update politician statuses - Q4 2024"
git push
```

---

## 📋 Common Update Scenarios

### Scenario 1: Politician Announces Retirement

**When:** Politician announces they won't seek re-election

**Effect:** Weight **BOOSTED** by 1.5x (lame duck urgency!)

**Example:** Brian Higgins announced November 8, 2024 that he'll leave February 1, 2025

```python
'Brian Higgins': {
    'action': 'set_retiring',
    'term_ended': '2025-02-01',
    'retirement_announced': '2024-11-08',
    'reason': 'Announced early retirement February 2025'
}
```

**Weight Change:**
- Before: 1.3x (base weight)
- After: 1.95x (1.3 × 1.5 boost)
- Trades now weighted 50% higher!

---

### Scenario 2: Politician Leaves Office

**When:** Term ends, politician has left

**Effect:** Time-decay begins (exponential decay over 90 days)

**Example:** Nancy Pelosi left leadership January 2023

```python
'Nancy Pelosi': {
    'action': 'set_retired',
    'term_ended': '2023-01-03',
    'retirement_announced': '2022-11-17',
    'reason': 'Left Speaker position, retired from leadership'
}
```

**Weight Change Over Time:**
- Day 0: 2.0x (full weight at retirement)
- Day 90: 1.0x (50% after half-life)
- Day 180: 0.5x (25% decay)
- Day 270+: 0.4x (20% floor)

---

### Scenario 3: Add New Politician

**When:** Discover new high-volume trader on Capitol Trades

**Effect:** Added to tracking with base weight

**Example:** New politician showing significant trading activity

```python
'Alexandria Ocasio-Cortez': {
    'action': 'add_new',
    'party': 'D',
    'office': 'House',
    'state': 'NY',
    'district': '14',
    'base_weight': 1.2,
    'reason': 'Consistent trading activity, notable positions'
}
```

**How to Determine Base Weight:**
- Start with 1.0x (default)
- Review trade history on Capitol Trades
- Check trade frequency, size, and outcomes
- Compare to existing tracked politicians
- Typical range: 1.0x - 2.0x

**Weight Guidelines:**
| Performance | Base Weight | Examples |
|-------------|-------------|----------|
| Legendary | 2.0x | Nancy Pelosi, Paul Pelosi |
| Excellent | 1.5-1.8x | Josh Gottheimer, Mark Green |
| Good | 1.2-1.4x | Dan Crenshaw, Tommy Tuberville |
| Average | 1.0x | Default for new additions |

---

### Scenario 4: Politician Returns to Office

**When:** Previously retired politician returns (rare)

**Effect:** Reactivated to full weight

```python
'Some Politician': {
    'action': 'set_active',
    'term_started': '2025-01-03',
    'reason': 'Re-elected after retirement'
}
```

---

## 🎯 Quick Reference: Status Transitions

```
┌──────────┐
│  ACTIVE  │ ←─────────────┐
│  (1.0x)  │                │ Returns to office
└────┬─────┘                │ (rare)
     │                      │
     │ Announces retirement │
     ▼                      │
┌──────────┐                │
│ RETIRING │                │
│  (1.5x)  │ ← BOOST!       │
└────┬─────┘                │
     │                      │
     │ Term ends            │
     ▼                      │
┌──────────┐                │
│ RETIRED  │                │
│ (decay)  │ ───────────────┘
└──────────┘
  ↓ (time-decay)
  Day 0:   1.00x (100%)
  Day 90:  0.50x (50%)
  Day 180: 0.25x (25%)
  Day 270: 0.20x (20% floor)
```

---

## 📊 Monitoring & Verification

### After Each Update

1. **Check Pipeline Output**
   ```bash
   # Next daily run will show:
   "Initializing politician tracker with time-decay..."
   "Tracking X politicians"
   "Active: Y, Retiring: Z, Retired: W"
   ```

2. **Verify Weights in Logs**
   ```
   "Applied time-decay weights from PoliticianTracker"
   ```

3. **Review Trade Signals**
   - Retiring politicians should show boosted weights
   - Retired politicians should show decayed weights

### Monthly Health Check

Run the test script to review current state:

```bash
cd /home/user/insider-cluster-watch
python jobs/test_time_decay.py
```

This shows:
- Current weights for all politicians
- Status breakdown
- Time-decay calculations
- Lame duck analysis

---

## 🚨 Important Reminders

### DO:
✅ Update status when retirements **announced** (to capture lame duck boost!)
✅ Verify dates from official sources (congress.gov)
✅ Commit changes to git after each update
✅ Run quarterly reviews even if no changes
✅ Check Capitol Trades for new high-volume traders

### DON'T:
❌ Delete politicians from registry (time-decay preserves data!)
❌ Forget to update `term_ended` dates
❌ Skip the quarterly review
❌ Add politicians without trade history
❌ Use unofficial sources for status info

---

## 📞 Troubleshooting

### Issue: "Politician not found in registry"

**Solution:** Use `'action': 'add_new'` instead of updating status

### Issue: Weight not changing as expected

**Solution:**
1. Check `term_ended` date format (must be ISO: `YYYY-MM-DD`)
2. Verify status is correct (`active`, `retiring`, `retired`)
3. Run test script to see current weights

### Issue: Update script won't run

**Solution:**
```bash
# Make script executable
chmod +x jobs/update_politician_status.py

# Or run with python explicitly
python jobs/update_politician_status.py
```

---

## 📚 Additional Resources

- **Politician Tracker Code:** `jobs/politician_tracker.py`
- **Registry File:** `data/politician_registry.json`
- **Test Script:** `jobs/test_time_decay.py`
- **Configuration:** `jobs/config.py` (lines 109-128)

---

## 🔄 Quarterly Checklist Template

Copy this for each quarterly review:

```markdown
## Q4 2024 Politician Status Review (Example)

**Date:** 2024-11-24
**Reviewer:** [Your Name]

### Sources Checked
- [ ] Congress.gov member directory
- [ ] Recent news (Politico, The Hill, Roll Call)
- [ ] Capitol Trades recent activity
- [ ] Retirement announcements

### Changes Made
1. Brian Higgins → Set to "retiring" (announced 11/8/24)
2. [Add more as needed]

### New Politicians Added
- [None this quarter]

### Politicians to Watch
- [Monitor for high trading activity]

### Next Review
- **Date:** January 15, 2025 (Q1 2025)
- **Focus:** Post-election updates, new Congress

### Notes
- [Any observations or patterns noticed]
```

---

## 📝 Change Log

| Date | Changes | Reviewer |
|------|---------|----------|
| 2024-11-24 | Initial registry with 11 politicians | System |
| YYYY-MM-DD | [Your updates here] | [Your name] |

---

**Questions or Issues?** Check `jobs/update_politician_status.py` usage guide or review the politician tracker documentation.
