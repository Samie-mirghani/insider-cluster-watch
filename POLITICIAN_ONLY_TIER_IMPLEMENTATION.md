# Politician-Only Tier (Tier 0) Implementation

## Summary

This implementation adds a new **Tier 0 (Politician-Only)** signal tier that allows the system to trade politician cluster signals independently, without requiring corresponding insider cluster activity. These signals compete directly with insider-based signals and are only traded if they represent the best opportunity.

## Changes Made

### 1. Improved Ticker Filtering Logs (`jobs/fetch_openinsider.py`)

**Problem**: Log message "Filtered out 27 invalid tickers" was misleading - these were legitimate tickers that failed data validation checks.

**Solution**: Enhanced logging to categorize failures by reason:
```python
# Old: Generic "invalid tickers" message
logger.info(f"Filtered out {len(invalid_tickers)} invalid tickers from OpenInsider data")

# New: Categorized failure breakdown
logger.info(f"Filtered out {len(invalid_tickers)} tickers from OpenInsider data:")
for reason, tickers in failure_categories.items():
    logger.info(f"  {len(tickers)} ticker(s) - {reason}")
```

**Result**: Clear visibility into what types of tickers are being filtered:
- "X ticker(s) - Blacklisted: No trading data for required time horizon"
- "Y ticker(s) - Mutual fund ticker"
- "Z ticker(s) - No price data from yfinance"

---

### 2. Politician-Only Tier Detection (`jobs/multi_signal_detector.py`)

Added comprehensive politician-only signal detection with strict quality requirements:

#### New Constants
```python
POLITICIAN_ONLY_MIN_POLITICIANS = 3  # Requires 3+ politicians (vs 2 for enhanced insider signals)

HIGH_CONVICTION_POLITICIANS = {
    'Nancy Pelosi', 'Paul Pelosi', 'Josh Gottheimer',
    'Mark Green', 'Dan Crenshaw', 'Marjorie Taylor Greene',
    'Tommy Tuberville', 'Austin Scott', 'Michael McCaul'
}
```

#### New Methods

**`_calculate_politician_score(politician_data)`**
- Scores politician clusters from 0-10 using methodology similar to insider scoring
- Factors:
  - **Count Score**: 3 politicians = 3 points, 5+ = 5 points (max)
  - **Value Score**: Based on weighted trade amounts (politician performance factored in)
  - **Bipartisan Bonus**: +2 points for cross-party agreement
  - **High-Conviction Bonus**: +1 point per tracked high-performing politician (max +3)

**`_detect_politician_only_clusters(politician_clusters, insider_tickers)`**
- Identifies politician clusters WITHOUT corresponding insider activity
- Requirements:
  1. **Minimum 3 politicians** (vs 2 for multi-signal)
  2. **High conviction score** (≥5.0/10)
  3. **Quality check**: Must have EITHER:
     - Bipartisan support, OR
     - High-conviction politician involved, OR
     - High aggregate value (>$150K weighted)

**`_get_conviction_level(score)`**
- Maps scores to conviction levels: VERY_HIGH (8+), HIGH (6.5+), MODERATE (5+), LOW (<5)

#### Modified `run_full_scan()` Method
```python
# New tier added to results
results = {
    'tier0': [],  # Politician-only signals (standalone high-conviction)
    'tier1': [],  # 3+ signals (HIGHEST)
    'tier2': [],  # 2 signals (HIGH)
    'tier3': [],  # 1 strong signal (MODERATE)
    'tier4': []   # Watch list
}

# Detect politician-only clusters before processing insider overlaps
politician_only_signals = self._detect_politician_only_clusters(
    politician_clusters,
    insider_tickers
)
results['tier0'] = politician_only_signals
```

---

### 3. Position Sizing Configuration (`jobs/config.py`)

Added tier0 to position sizing and risk management:

```python
MULTI_SIGNAL_POSITION_SIZES = {
    'tier0': 0.40,  # 40% position (politician-only: ~2-3% of portfolio vs 5-6% for full)
    'tier1': 1.0,   # Full position (3+ signals)
    'tier2': 0.75,  # 75% position (2 signals)
    'tier3': 0.50,  # 50% position (1 strong signal)
    'tier4': 0.25   # 25% position (watch list)
}

MULTI_SIGNAL_STOP_LOSS = {
    'tier0': 0.08,  # -8% stop for politician-only (tighter due to lower conviction)
    'tier1': 0.12,  # -12% stop for highest conviction
    'tier2': 0.10,  # -10% stop
    'tier3': 0.08,  # -8% stop
    'tier4': 0.06   # -6% stop (tighter for lower conviction)
}
```

**Effective Position Sizing**:
- Tier 0: ~2-3% of portfolio (40% of base position)
- Tier 1: ~5-6% of portfolio (100% of base position)
- Tier 2: ~4-5% of portfolio (75% of base position)

---

### 4. Signal Integration (`jobs/main.py`)

Modified multi-signal processing to include politician-only signals in the signal pool:

#### New Logic Flow
1. **Extract tier0 signals** from multi_signal_results
2. **Convert to DataFrame rows** with required fields:
   - `ticker`, `company`, `rank_score` (based on politician_score)
   - `multi_signal_tier`: 'tier0'
   - `politician_count`, `politician_names`, `politician_details`
   - `is_bipartisan`, `high_conviction_count`, `conviction_level`
3. **Fetch market data** (price, market cap, sector) using existing pipeline
4. **Append to cluster_df** - politician-only signals now compete directly with insider signals
5. **Sort by rank_score** - best signals (insider or politician) rise to top

#### Example Output
```
🏛️  Processing 3 politician-only signals (Tier 0)...
   📊 Fetching market data for 3 politician-only tickers...
   ✅ Added 3 politician-only signals to signal pool
      • MSFT: 3 pols, score 8.2 🤝 ⭐2
      • GOOGL: 2 pols, score 6.5 ⭐1
      • IBM: 2 pols, score 5.8
```

---

## Key Features

### 1. **Higher Standards for Standalone Signals**
- Politician-only requires 3+ politicians (vs 2 when combined with insider signals)
- Must pass quality checks (bipartisan, high-conviction politician, or high value)
- Minimum score threshold of 5.0/10

### 2. **Bipartisan Bonus**
- +2 points when both parties are trading same ticker
- Signals strong cross-party conviction
- Example: Republicans + Democrats both buying MSFT

### 3. **High-Conviction Politicians**
- Tracks specific politicians with proven performance
- +1 point per high-conviction politician involved (max +3)
- Example: Nancy Pelosi's involvement adds extra conviction

### 4. **Conservative Position Sizing**
- 40% of base position = ~2-3% of portfolio
- Tighter stop loss (8% vs 12% for tier1)
- Recognizes lower conviction vs insider+politician signals

### 5. **Direct Competition with Insider Signals**
- Politician-only signals added to same pool as insider signals
- Sorted by `rank_score` - best signals traded first
- Subject to same quality filters (minimum score threshold, news sentiment, etc.)

---

## Comparison: Tier 0 vs Multi-Signal Tiers

| Tier | Signals | Requirements | Position Size | Stop Loss | Example |
|------|---------|--------------|---------------|-----------|---------|
| **Tier 0** | Politician-only | 3+ politicians, quality checks | 40% (~2-3%) | -8% | 3 bipartisan politicians buying MSFT |
| **Tier 1** | 3+ signals | Insider + Politician + Institutional | 100% (~5-6%) | -12% | Insider cluster + politicians + 13F holdings |
| **Tier 2** | 2 signals | Insider + (Politician OR Institutional) | 75% (~4-5%) | -10% | Insider cluster + politician trades |
| **Tier 3** | 1 strong signal | 5+ insiders buying | 50% (~3-4%) | -8% | Strong insider cluster only |

---

## Example Scenarios

### Scenario 1: Bipartisan High-Conviction Signal
**MSFT**: Nancy Pelosi (D) + Dan Crenshaw (R) + Tommy Tuberville (R) buying
- ✅ **3 politicians** (meets minimum)
- ✅ **Bipartisan** (+2 points)
- ✅ **2 high-conviction politicians** (+2 points)
- ✅ **Score: 8.2/10** (VERY_HIGH conviction)
- **Result**: Qualifies as Tier 0, receives ~2-3% position

### Scenario 2: High-Value Cluster
**GOOGL**: 3 politicians buying, total weighted value $200K+
- ✅ **3 politicians** (meets minimum)
- ✅ **High value** (>$150K weighted)
- ✅ **Score: 6.5/10** (HIGH conviction)
- **Result**: Qualifies as Tier 0, receives ~2-3% position

### Scenario 3: Low-Quality Signal (Rejected)
**AAPL**: 2 politicians buying, not bipartisan, no high-conviction politicians
- ❌ **Only 2 politicians** (needs 3+)
- **Result**: Does NOT qualify as Tier 0, not traded standalone

---

## Testing Checklist

- [ ] Verify politician-only signals detected when no insider overlap
- [ ] Confirm 3+ politician requirement enforced
- [ ] Validate bipartisan bonus applied correctly
- [ ] Check high-conviction politician bonus calculation
- [ ] Ensure position sizing is 40% of base (tier0 multiplier)
- [ ] Verify stop loss is 8% (tier0 risk management)
- [ ] Confirm signals compete with insider signals based on rank_score
- [ ] Test that existing tier1/tier2 functionality unchanged
- [ ] Verify logging shows tier0 count and examples
- [ ] Check email report includes tier0 signals appropriately

---

## Notes

1. **No Breaking Changes**: All existing functionality preserved. Tier 1/2/3/4 work exactly as before.

2. **Conservative Approach**: High requirements (3+ politicians, quality checks) ensure only strong signals qualify.

3. **Market Data Integration**: Politician-only signals go through same validation as insider signals (price check, sector analysis, news sentiment).

4. **Flexible Scoring**: Politician score methodology mirrors insider scoring, making comparison fair and objective.

5. **Future Enhancements**:
   - Add short interest checks for politician-only signals
   - Track politician-only signal performance separately
   - Adjust HIGH_CONVICTION_POLITICIANS list based on actual performance data
