# Data Protection Safeguards

This document outlines the multiple layers of protection implemented to prevent data corruption and portfolio resets.

## Incident History

**2026-01-12**: Paper trading portfolio was corrupted by git merge conflict markers during automated rebase. The portfolio JSON file contained `<<<<<<< HEAD` markers which caused JSON parsing to fail. The original error handler silently reset the portfolio to default state ($10,000 starting capital, 0 trades), wiping out the actual portfolio state (36 trades, $1,216 profit, 61% win rate).

## Protection Layers

### 1. Pre-Job Data Validation (`jobs/validate_data_integrity.py`)

**What it does:**
- Scans all data files for git merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- Validates JSON files can be parsed correctly
- Checks CSV files have proper structure
- Validates paper_portfolio.json has required fields and reasonable values
- Detects if portfolio appears to be in reset state

**When it runs:**
- **BEFORE** every main job execution (enforced in GitHub workflow)
- Can be run manually: `python jobs/validate_data_integrity.py`

**What happens on failure:**
- Job execution is aborted
- Error details are logged
- Manual intervention required

### 2. Defensive Portfolio Loading (`jobs/paper_trade.py`)

**Original behavior (DANGEROUS):**
```python
except Exception as e:
    logger.error(f"Error loading portfolio: {e}")
    logger.info("Creating new portfolio")
    return cls()  # SILENTLY RESETS PORTFOLIO!
```

**New behavior (SAFE):**
```python
except Exception as e:
    logger.error(f"CRITICAL ERROR loading portfolio: {e}")

    # Check for merge conflict markers
    if '<<<<<<< HEAD' in file_content:
        logger.error("MERGE CONFLICT MARKERS DETECTED!")
        raise RuntimeError("Manual fix required")

    # Create backup of corrupted file
    backup_path = f"{file}.corrupt.{timestamp}.bak"
    shutil.copy(file, backup_path)

    # Log detailed error information
    logger.error(f"File backed up to: {backup_path}")

    # ABORT - DO NOT RESET PORTFOLIO
    raise RuntimeError(f"Failed to load portfolio: {e}")
```

**Protection:**
- NO automatic portfolio reset
- Creates backup of corrupted file with timestamp
- Logs detailed error information
- Forces job to abort (manual intervention required)

### 3. Git Workflow Safeguards (`.github/workflows/daily_job.yml`)

**Before Job Execution:**
```yaml
- name: Validate data integrity before job execution
  run: |
    python jobs/validate_data_integrity.py
    if [ $? -ne 0 ]; then
      echo "Data integrity validation failed! Aborting."
      exit 1
    fi
```

**Improved Rebase Handling:**
```yaml
# OLD (DANGEROUS):
git pull --rebase origin main || true  # Ignores conflicts!
git stash pop || true                   # Ignores conflicts!

# NEW (SAFE):
if git pull --rebase origin main; then
  echo "Rebase successful"
else
  echo "Rebase had conflicts, aborting rebase"
  git rebase --abort
  echo "Using merge strategy instead"
  git pull --no-rebase origin main
fi
```

**Post-Rebase Validation:**
```yaml
# Check for merge conflict markers after rebase
if grep -r "<<<<<<< HEAD" data/; then
  echo "CRITICAL: Merge conflict markers detected!"
  echo "Aborting commit and push."
  exit 1
fi
```

### 4. Manual Recovery Procedures

**If portfolio corruption is detected:**

1. **Automated backup:** Check for `data/paper_portfolio.json.corrupt.YYYYMMDD_HHMMSS.bak`

2. **Git history recovery:**
   ```bash
   # Find last good commit
   git log --all --oneline --follow data/paper_portfolio.json

   # Restore from specific commit
   git show <commit-hash>:data/paper_portfolio.json > data/paper_portfolio.json
   ```

3. **Validate restored portfolio:**
   ```bash
   python jobs/validate_data_integrity.py
   ```

4. **Verify stats match dashboard:**
   - Check cash balance
   - Count completed trades in `paper_trades.csv`
   - Verify active positions
   - Confirm win rate calculation

## Testing the Safeguards

**Simulate merge conflict:**
```bash
# Add conflict markers to portfolio (in a test branch!)
echo '<<<<<<< HEAD' >> data/paper_portfolio.json

# Run validation
python jobs/validate_data_integrity.py
# Should fail with clear error message

# Try to load portfolio
python -c "from jobs.paper_trade import PaperTradingPortfolio; PaperTradingPortfolio.load()"
# Should abort with error, NOT reset portfolio
```

## Key Principles

1. **Fail Fast:** Detect corruption immediately, before jobs run
2. **Never Silent Reset:** Always abort instead of silently resetting data
3. **Create Backups:** Preserve corrupted state for forensics
4. **Detailed Logging:** Log enough info to understand what went wrong
5. **Manual Recovery:** Force human review for data corruption issues

## Monitoring

**Signs of data corruption:**
- Job failures with "merge conflict markers" errors
- JSON parsing errors in logs
- Portfolio validation warnings
- Backup files appearing (`*.corrupt.*.bak`)

**Where to check:**
- GitHub Actions workflow logs
- `data/paper_trading.log`
- Backup files in `data/` directory
- Git commit history for anomalies

## Future Improvements

1. **Automated alerts:** Send email/notification on data corruption detection
2. **Pre-commit hooks:** Block local commits with conflict markers
3. **Data checksums:** Validate data integrity using checksums
4. **Redundant storage:** Keep offsite backup of portfolio state
5. **Rollback automation:** Automatic recovery from last known good state

## Contact

If you encounter data corruption issues, check:
1. GitHub Actions logs for the failed workflow
2. `data/paper_trading.log` for detailed error messages
3. Backup files (`*.corrupt.*.bak`) for recovery
4. Git history for last known good state

**Never manually reset the portfolio without first attempting recovery from backups or git history.**
