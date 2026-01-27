# Fix critical DataFrame index alignment bug in sector analysis

## 🐛 Critical Bug Fix: Sector Assignment Misalignment

This PR fixes a critical DataFrame index alignment bug that was causing sector classifications to be assigned to the wrong tickers in the daily signal reports.

## 🔍 Problem Discovery

During today's signal processing (2026-01-27), the following incorrect sector assignments were discovered:
- **GME (GameStop)**: Assigned sector "Steel" ✗ (Correct: "Specialty Retail")
- **MIGI**: Assigned sector "Specialty Retail" ✗ (Correct: "Financial - Capital Markets")

All other tickers (BDSX, ABT, UAA) had `sector=None` despite valid industry data being available.

## 🎯 Root Cause

The bug occurs in `jobs/sector_analyzer.py` at line 792-800 in the `enhance_signals_with_sector_analysis()` method.

**The Problem:**
```python
# BUGGY CODE (before fix)
sector_df = pd.DataFrame(sector_data)  # Sequential index: [0, 1, 2, 3, 4]

# Direct assignment causes pandas to align BY INDEX, not position
signals_df['sector'] = sector_df['sector']  # ❌ WRONG!
```

**What happens:**
1. After filtering/sorting, `signals_df` has a **non-sequential index** (e.g., `[5, 10, 2, 15, 3]`)
2. `sector_df` is created from a list, so it has a **sequential index** (e.g., `[0, 1, 2, 3, 4]`)
3. Pandas assignment aligns DataFrames **by index**, not by position
4. Row at index `2` in `signals_df` gets the value from index `2` in `sector_df`
5. But index `2` in `signals_df` might be the 3rd ticker processed, while index `2` in `sector_df` is the 3rd row created
6. **Result**: Sectors get assigned to completely wrong tickers! 💥

**Visual Example:**
```
signals_df (after filtering):          sector_df (newly created):
Index  Ticker  Sector                  Index  Sector
-----  ------  ------                  -----  ------
  5    BDSX    None      ←──────×──→     0    Healthcare
 10    GME     None      ←──────×──→     1    Specialty Retail
  2    ABT     None      ←──────×──→     2    Healthcare
 15    MIGI    None      ←──────×──→     3    Financial Services
  3    UAA     None      ←──────×──→     4    Consumer Cyclical

After buggy assignment (aligns by index):
signals_df['sector'] = sector_df['sector']

Index  Ticker  Sector (WRONG!)
-----  ------  ----------------
  5    BDSX    None             (no match for index 5 in sector_df)
 10    GME     None             (no match for index 10 in sector_df)
  2    ABT     Healthcare       (got value from sector_df index 2 - WRONG TICKER!)
 15    MIGI    None             (no match for index 15 in sector_df)
  3    UAA     Consumer Cyclical (got value from sector_df index 3 - WRONG TICKER!)
```

This is why GME ended up with "Steel" - it got a sector from a completely different row due to index misalignment!

## ✅ The Fix

**Solution**: Use `.values` to force **positional assignment** instead of index-based alignment.

```python
# FIXED CODE
sector_df = pd.DataFrame(sector_data)  # Sequential index: [0, 1, 2, 3, 4]

# Use .values to force positional assignment (ignores index)
signals_df['sector'] = sector_df['sector'].values  # ✅ CORRECT!

# Also fix all other columns being transferred
for col in ['sector_etf', 'relative_performance_30d', ...]:
    if col in sector_df.columns:
        signals_df[col] = sector_df[col].values  # ✅ CORRECT!
```

By using `.values`, we extract the underlying NumPy array, which has no index. This forces pandas to assign values **by position** (row 0 → row 0, row 1 → row 1, etc.), which is what we actually want.

## 📋 Changes Made

**File**: `jobs/sector_analyzer.py`
- **Line 799**: Changed `signals_df['sector'] = sector_df['sector']` → `signals_df['sector'] = sector_df['sector'].values`
- **Line 806**: Changed `signals_df[col] = sector_df[col]` → `signals_df[col] = sector_df[col].values`
- Added detailed comment explaining the fix and why `.values` is necessary

## 🧪 Testing

This fix can be verified by:
1. Running signal processing with multiple signals
2. Checking that sector assignments match the correct industry data
3. Verifying `signals_history.csv` shows correct sectors going forward

## 📊 Impact

✅ **Immediate**: All future signal processing will have correct sector assignments
❌ **Historical**: Previous data in `signals_history.csv` contains incorrect sectors (Jan 27 and earlier)

**Note**: Historical data does not need correction as it doesn't impact future trading decisions.

## 🎓 Lesson Learned

**Always use `.values` when assigning between DataFrames with potentially different indices:**
```python
# WRONG (index-aligned):
df1['col'] = df2['col']

# CORRECT (position-aligned):
df1['col'] = df2['col'].values
```

This is especially important when:
- One DataFrame has been filtered/sorted (non-sequential index)
- The other DataFrame was just created from a list (sequential index)
- You want to maintain the original row order

## 🔗 Related Issues

This also addresses the question of why MIGI and UAA were in `approved_signals.json` - they were **legitimate signals** that passed all quality filters. The approved signals export is working correctly; only the sector assignment had this bug.

---

**Commit**: `4693578`
**Branch**: `claude/debug-signals-sectors-gRY5k`
**Base**: `main`
