# GitHub Pages Setup Guide

This guide will help you enable and configure the GitHub Pages performance dashboard.

## ✅ What's Included

### 1. **Public Performance Tracker** (`jobs/generate_public_performance.py`)
- Generates `public_performance.json` with aggregated performance data
- **NO sensitive dollar amounts** - only percentages and statistics
- Updates automatically with each daily run
- Includes:
  - Total return %
  - Win rate
  - Completed trades count
  - Active positions count
  - Average return per trade
  - Sharpe ratio
  - Recent 20 closed trades (with details)
  - Current open positions

### 2. **Realistic Paper Trading Settings** (`jobs/config.py`)
Your paper trading now includes:
- ✅ Market hours validation (9:30 AM - 4:00 PM ET)
- ✅ Realistic entry slippage (0.10-0.30% based on liquidity)
- ✅ Commission costs (configurable, default $0)
- ✅ Trail stop execution slippage (0.20%)
- ✅ Next-day open price entry (no perfect timing)

**Configuration Variables Added:**
```python
REALISTIC_TRADING_MODE = True
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
TRADING_COMMISSION_PER_SHARE = 0.0
TRADING_SLIPPAGE_PCT = 0.15
USE_OPENING_PRICE_FOR_ENTRY = True
```

### 3. **Professional Landing Page** (`index.html`)
Beautiful, responsive GitHub Pages site featuring:
- ✅ Real-time performance statistics
- ✅ Recent closed trades table
- ✅ Current open positions
- ✅ Email signup form integration
- ✅ Mobile-responsive design
- ✅ Professional gradient design with Inter font
- ✅ Animated loading states
- ✅ Performance-focused (highlights wins!)

---

## 🚀 Enable GitHub Pages

### Step 1: Enable GitHub Pages in Repository Settings

1. Go to your repository on GitHub: `https://github.com/Samie-mirghani/insider-cluster-watch`

2. Click **Settings** (top menu)

3. Scroll down to **Pages** (left sidebar)

4. Under **Source**, select:
   - **Source:** Deploy from a branch
   - **Branch:** `main`
   - **Folder:** `/ (root)`

5. Click **Save**

6. Wait 1-2 minutes for deployment

7. Your site will be live at:
   ```
   https://samie-mirghani.github.io/insider-cluster-watch/
   ```

### Step 2: Verify Deployment

1. Visit your GitHub Pages URL

2. You should see the landing page with:
   - Performance statistics (may show 0s initially)
   - "Loading performance data" messages

3. After the first daily run (7 AM ET), `public_performance.json` will be generated and the stats will populate

---

## 📧 Set Up Email Signup (Optional)

The landing page includes an email signup form. To make it functional:

### Option 1: Formspree (Easiest - Free)

1. Go to [Formspree.io](https://formspree.io)

2. Sign up for a free account

3. Create a new form

4. Copy your form endpoint (looks like: `https://formspree.io/f/xyzabc123`)

5. Edit `index.html` and replace:
   ```html
   <form class="signup-form" action="https://formspree.io/f/YOUR_FORMSPREE_ID" method="POST">
   ```
   with your actual Formspree ID

6. Commit and push the change

Now when users subscribe, you'll get email notifications!

### Option 2: Mailchimp, ConvertKit, or Other

Replace the form `action` URL with your email service provider's endpoint.

---

## 📊 How the Data Flow Works

```
Daily Run (7 AM ET)
    ↓
jobs/main.py executes
    ↓
Paper trades are updated
    ↓
jobs/generate_public_performance.py runs
    ↓
public_performance.json is generated
    ↓
Git commits the JSON file
    ↓
GitHub Pages automatically refreshes
    ↓
Website shows updated stats (within 1-2 min)
```

---

## 🎨 Customizing the Landing Page

### Change Colors

Edit the CSS variables in `index.html`:
```css
:root {
    --primary: #667eea;      /* Main purple */
    --primary-dark: #5568d3;
    --secondary: #764ba2;    /* Gradient purple */
    --success: #10b981;      /* Green for wins */
    --danger: #ef4444;       /* Red for losses */
}
```

### Add Your Logo

Replace the 📊 emoji in the header:
```html
<h1>📊 Insider Cluster Watch</h1>
```

with an image:
```html
<h1><img src="logo.png" alt="Logo"> Insider Cluster Watch</h1>
```

### Update Content

All text in `index.html` can be edited directly. Key sections:
- **Line 209:** Main headline
- **Line 210:** Subtitle
- **Line 211:** Tagline
- **Line 226-230:** CTA section
- **Line 240-280:** Features grid

---

## 🧪 Testing Locally

### View the Site Locally

1. Install a simple HTTP server:
   ```bash
   python3 -m http.server 8000
   ```

2. Open browser to:
   ```
   http://localhost:8000
   ```

3. The site will load (but `public_performance.json` needs to exist)

### Generate Test Performance Data

```bash
python jobs/generate_public_performance.py
```

This creates `public_performance.json` based on current paper trading data.

---

## 📈 Performance Tracking Details

### What Gets Tracked

**Public (Shown on Website):**
- ✅ Total return percentage
- ✅ Win rate
- ✅ Number of trades
- ✅ Average return per trade
- ✅ Sharpe ratio
- ✅ Recent trades (ticker, dates, returns %)
- ✅ Open positions (ticker, days held, unrealized %)

**Private (NOT Shown):**
- ❌ Dollar amounts
- ❌ Position sizes
- ❌ Exact entry/exit prices
- ❌ Portfolio value

This protects your privacy while demonstrating performance!

### Conviction Levels

Signals are labeled by conviction:
- **VERY HIGH:** Signal score ≥ 15
- **HIGH:** Signal score ≥ 10
- **MEDIUM:** Signal score ≥ 7
- **LOW:** Signal score ≥ 5
- **WATCH:** Signal score < 5

---

## 🔧 Troubleshooting

### Site Shows "Error Loading Data"

**Cause:** `public_performance.json` doesn't exist yet

**Fix:**
1. Wait for daily run (7 AM ET)
2. OR manually run:
   ```bash
   python jobs/generate_public_performance.py
   git add public_performance.json
   git commit -m "Add initial performance data"
   git push
   ```

### Stats Show All Zeros

**Cause:** No trade history yet (system just started)

**Fix:** Wait for trades to execute. This is normal for a new system.

### GitHub Pages Not Updating

**Cause:** Deployment delay (1-2 minutes)

**Fix:**
1. Check GitHub Actions tab for successful workflow
2. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
3. Wait 2-3 minutes and try again

### Form Submissions Not Working

**Cause:** Formspree ID not configured

**Fix:** Follow "Set Up Email Signup" instructions above

---

## 🎯 Next Steps

1. ✅ Enable GitHub Pages (see Step 1 above)

2. ✅ Wait for tomorrow's 7 AM ET run (or manually run the script)

3. ✅ Share your GitHub Pages URL with potential subscribers!

4. ✅ Optional: Set up email signup with Formspree

5. ✅ Optional: Customize colors/branding

---

## 📱 Mobile Responsive

The landing page is fully responsive and looks great on:
- ✅ Desktop (1920px+)
- ✅ Laptop (1366px)
- ✅ Tablet (768px)
- ✅ Mobile (375px)

Test it by resizing your browser window!

---

## 🚀 Go Live Checklist

- [ ] Enable GitHub Pages in repository settings
- [ ] Wait for first deployment (1-2 minutes)
- [ ] Visit your GitHub Pages URL
- [ ] Run first data generation: `python jobs/generate_public_performance.py`
- [ ] Commit and push `public_performance.json`
- [ ] Verify stats appear on website
- [ ] Optional: Configure Formspree for email signups
- [ ] Optional: Customize branding/colors
- [ ] Share your URL: `https://samie-mirghani.github.io/insider-cluster-watch/`

---

## 🎉 You're Done!

Your professional performance tracking dashboard is now live and updating automatically every day!

**Your URL:**
```
https://samie-mirghani.github.io/insider-cluster-watch/
```

Share this with potential subscribers to showcase your system's real-world performance!
