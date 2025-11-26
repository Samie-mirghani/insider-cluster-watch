# Congress.gov API Key Setup Guide

## Why You Need This

The automated politician status checker uses the official Congress.gov API to automatically detect when politicians leave office. This eliminates manual maintenance of the politician registry.

**Without the API key:** You'll see a warning and automated checks will be skipped (not critical, but recommended).

**With the API key:** Automatic daily checks keep your politician registry up-to-date.

---

## Setup Instructions (2 minutes)

### Step 1: Get Your Free API Key

1. Go to: **https://api.congress.gov/sign-up/**
2. Fill out the simple form:
   - Email address
   - First name
   - Last name
   - Organization (can be "Personal" or "Individual")
3. Check your email for the API key (arrives instantly)

### Step 2: Configure the API Key

**Option A: Using .env file (Recommended)**

```bash
# Copy the example file
cp .env.example .env

# Edit .env and replace 'your-api-key-here' with your actual key
nano .env  # or use your preferred editor
```

Your `.env` file should look like:
```
CONGRESS_GOV_API_KEY=abcd1234-5678-90ef-ghij-klmnopqrstuv
```

**Option B: Using environment variable**

```bash
# Add to your ~/.bashrc or ~/.zshrc
export CONGRESS_GOV_API_KEY="your-api-key-here"

# Or set temporarily for current session
export CONGRESS_GOV_API_KEY="your-api-key-here"
```

**Option C: Hardcode in config (NOT recommended for git repos)**

Edit `jobs/config.py`:
```python
CONGRESS_GOV_API_KEY = "your-api-key-here"
```

⚠️ **Warning:** Don't commit API keys to git! Use Options A or B instead.

### Step 3: Verify It Works

Run the paper trading system and check the logs. You should see:

```
✅ BEFORE (no API key):
   • Running automated politician status check...
     ⚠️  No Congress.gov API key - skipping auto-check
     ℹ️  Get free key at: https://api.congress.gov/sign-up/

✅ AFTER (with API key):
   • Running automated politician status check...
     - Checked 11 politicians
     - All statuses up-to-date
```

---

## API Key Details

- **Rate Limits:** 5,000 requests/hour (free tier)
- **Cost:** FREE forever
- **Usage:** ~1-5 requests per day for this system
- **Privacy:** Your key is stored locally and never shared
- **Security:** .env file is in .gitignore (won't be committed)

---

## Troubleshooting

### "No API key" warning persists

1. **Check environment variable:**
   ```bash
   echo $CONGRESS_GOV_API_KEY
   ```
   Should output your API key (not blank)

2. **Check .env file:**
   ```bash
   cat .env
   ```
   Should contain: `CONGRESS_GOV_API_KEY=your-key`

3. **Restart your terminal/session** after setting environment variables

### API requests failing

1. **Verify API key is valid:**
   ```bash
   curl "https://api.congress.gov/v3/member?api_key=YOUR_KEY_HERE"
   ```
   Should return JSON (not an error)

2. **Check rate limits:** 5,000/hour should never be hit with normal usage

3. **Check internet connection:** API requires internet access

---

## Optional: Disable Automated Checks

If you prefer not to use the automated status checker:

Edit `jobs/config.py`:
```python
ENABLE_AUTOMATED_POLITICIAN_STATUS_CHECK = False
```

The system will continue working normally, but you'll need to manually update politician statuses in `data/politician_registry.json` when they retire.

---

## Support

- **Congress.gov API Docs:** https://api.congress.gov/
- **GitHub Issues:** https://github.com/LibraryOfCongress/api.congress.gov/issues
- **API Support:** congress.api@loc.gov
