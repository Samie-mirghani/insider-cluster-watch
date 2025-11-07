# Testing Guide for Email Template Fixes

This guide will help you verify all the fixes work correctly before merging to your main repo.

## What Was Fixed

1. ✅ **Static Date** - Already fixed in commit `789b095` (date now updates dynamically)
2. ✅ **Signal Count** - Changed from hardcoded "1" to actual count
3. ✅ **Insider Count** - Changed from hardcoded "(3 TOTAL)" to actual count
4. ✅ **Layout Issue** - Fixed multiple signals appearing with duplicate footers
5. ✅ **Deduplication** - Added transaction deduplication to prevent data inflation

## Quick Test (Recommended)

Run the comprehensive test suite:

```bash
cd /home/user/insider-cluster-watch
python3 test_urgent_email.py
```

This will:
- Test single signal (verify singular text)
- Test multiple signals (verify plural text and layout)
- Test transaction deduplication
- Optionally send test emails to your inbox

## Manual Testing Options

### Option 1: Generate Test Urgent Email (Built-in)

The existing test mode generates a single fake signal:

```bash
cd /home/user/insider-cluster-watch/jobs
python3 main.py --urgent-test
```

This will send an email with 1 signal. Check that:
- Date shows current date (not "October 17, 2025")
- Shows "1 high-conviction insider buying cluster detected" (singular)
- Shows correct insider count in the signal card

### Option 2: Run Full Pipeline in Test Mode

Run the actual pipeline with test emails:

```bash
cd /home/user/insider-cluster-watch/jobs
python3 main.py --test
```

This will:
- Fetch real insider trading data
- Process and cluster transactions
- Send emails with "TEST" prefix
- Show deduplication stats if duplicates are found

### Option 3: Visual HTML Review

Save the HTML to a file for inspection:

```bash
cd /home/user/insider-cluster-watch
python3 -c "
import sys
sys.path.insert(0, 'jobs')
import pandas as pd
from generate_report import render_urgent_html

# Create test data with 2 signals
data = pd.DataFrame([
    {'ticker': 'MTDR', 'cluster_count': 13, 'total_value': 1408102,
     'avg_conviction': 15.2, 'rank_score': 30.97,
     'insiders': 'CEO, CFO, and 11 others',
     'currentPrice': 37.94, 'pct_from_52wk_low': 12.3,
     'last_trade_date': pd.Timestamp.now(),
     'suggested_action': 'URGENT: Consider small entry',
     'rationale': 'Test signal 1'},
    {'ticker': 'AMRZ', 'cluster_count': 3, 'total_value': 6213440,
     'avg_conviction': 14.1, 'rank_score': 10.03,
     'insiders': 'CEO, CFO, Director',
     'currentPrice': 45.20, 'pct_from_52wk_low': 9.8,
     'last_trade_date': pd.Timestamp.now(),
     'suggested_action': 'URGENT: Consider small entry',
     'rationale': 'Test signal 2'}
])

html, _ = render_urgent_html(data)

with open('test_urgent_email.html', 'w') as f:
    f.write(html)
print('✅ Saved to test_urgent_email.html')
"
```

Then open `test_urgent_email.html` in your browser and verify:
- Header shows "2 high-conviction insider buying clusters detected" (plural)
- First signal shows "(13 TOTAL)" insiders
- Second signal shows "(3 TOTAL)" insiders
- Footer appears only once at the bottom
- Proper spacing between the two signal cards

## What to Check

### ✅ Signal Count
- Single signal: "1 high-conviction insider buying cluster detected" (singular)
- Multiple signals: "X high-conviction insider buying clusters detected" (plural)

### ✅ Insider Count
Each signal card should show the actual number:
- "(13 TOTAL)" for MTDR
- "(3 TOTAL)" for another signal
- NOT hardcoded "(3 TOTAL)" for all signals

### ✅ Layout with Multiple Signals
- All signal cards should appear in a single email
- Footer should appear ONCE at the bottom (not between signals)
- Nice spacing between signal cards
- No weird breaks or formatting issues

### ✅ Date
- Header should show current date like "November 07, 2025"
- NOT "October 17, 2025"

### ✅ Deduplication
When running the pipeline, watch for:
```
ℹ️  Removed X duplicate transactions
```

This means duplicate data was detected and removed (working correctly).

## Environment Setup

Make sure your `.env` file has these variables set for email testing:

```bash
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-specific-password
RECIPIENT_EMAIL=your-email@gmail.com
```

## Next Steps After Testing

### If All Tests Pass ✅

1. **Merge to main branch:**
   ```bash
   git checkout main
   git merge claude/fix-urgent-email-template-011CUtjtstc6r5rYTe7SSzJ8
   git push origin main
   ```

2. **Deploy to production** (if using GitHub Actions, it will auto-run)

3. **Monitor next urgent email** to verify fixes in production

### If Any Tests Fail ❌

1. Review the failed test output
2. Check the relevant files:
   - `templates/urgent_alert.html` - Template issues
   - `jobs/process_signals.py` - Deduplication issues
   - `jobs/generate_report.py` - Date/data passing issues

3. Report issues and I'll help fix them!

## Verifying in Production

After merging, the next urgent email will show:
- Dynamic date
- Correct signal count
- Correct insider counts
- Clean layout with multiple signals

You can also check the GitHub Actions logs for:
```
ℹ️  Removed X duplicate transactions
```

This confirms deduplication is working in production.

## Questions or Issues?

If you encounter any problems during testing, check:
1. Python dependencies are installed (`pip install -r requirements.txt`)
2. `.env` file is properly configured
3. Template files haven't been modified outside of the fixes

The test suite should help you catch any issues before merging!
