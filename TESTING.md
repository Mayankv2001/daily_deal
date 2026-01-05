# Testing Guide for Daily Deal Stack Reports

## Setup (One-time)

### 1. Install Dependencies

The project uses a virtual environment to avoid conflicts with system Python:

```bash
# Create virtual environment (already done)
python3 -m venv venv

# Activate it (required each time you work)
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

**Note**: Always activate the venv before running the scripts:
```bash
source venv/bin/activate
```

---

## Testing Options

### Option 1: Print Mode (No Email Sent)

Test the reports without sending emails. Output goes to terminal:

```bash
# Activate venv first
source venv/bin/activate

# Comprehensive deal report (all keyword-filtered deals)
python daily_deal_report.py --print

# Top 5 stack deals with recipes and scoring
python daily_stack_deal_report.py --print

# Limit output to first 100 lines for quick preview
python daily_deal_report.py --print | head -100
```

---

### Option 2: Send Test Email

Configure SMTP environment variables, then run without `--print`:

```bash
# Set up email credentials (Gmail example)
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="465"
export SMTP_USER="your-email@gmail.com"
export SMTP_PASS="your-app-password"  # Use app-specific password, not your Gmail password
export MAIL_TO="recipient@example.com"

# Activate venv
source venv/bin/activate

# Send actual emails
python daily_stack_deal_report.py    # Top 5 report
python daily_deal_report.py          # Comprehensive report
```

**Gmail App Password**: Go to Google Account → Security → 2-Step Verification → App passwords

---

### Option 3: Run Unit Tests

Test individual components without fetching live data:

```bash
source venv/bin/activate

# Test Apple chip detection
python test_apple_chip_integration.py

# Test stack recipe generation
python test_stack_recipe.py

# Test Harvey Norman integration
python test_harvey_norman.py

# Test arbitrage detection
python test_arbitrage_detection.py

# Test email output formatting
python test_email_output.py
python test_cashback_email_output.py
```

---

## What to Look For

### Comprehensive Report (`daily_deal_report.py`)

Expected features:
- **Keywords**: Filters deals containing gift cards, cashback, points promos, specific merchants
- **Sections**: FreePoints (top 10), GCDB (top 10), OzBargain (top 6 + 10 trending)
- **Stack hints**: Explains why deals are stackable (e.g., "Points promo on gift cards → buy Ultimate → use at JB Hi-Fi")
- **Merchant detection**: Shows detected merchants after deal titles
- **Cashback warnings**: Yellow warning boxes when cashback portals detected (⚠️ "ShopBack typically excludes gift card purchases")
- **Apple chip detection**: Identifies M1/M2/M3/M4 chips in deal titles
- **Confidence scoring**: HIGH (chip + physical retailer + stock), MEDIUM, or LOW

### Top 5 Stack Report (`daily_stack_deal_report.py`)

Expected features:
- **Scoring system**: Ranks deals by stack potential (0-20 points)
  - 20x+ points = 8-10 pts
  - Gift cards = +3 pts
  - Priority merchants (Officeworks, JB Hi-Fi, Apple, etc.) = +2 pts
  - Arbitrage eligible = +1-4 pts
  - Cashback = +1 pt (reduced from +2-3)
  - Competitions/wins = -3 pts
- **Stack recipes**: 3-5 step instructions for each top deal
  - Step 1: Activate points
  - Step 2: Buy gift cards
  - Step 3: Convert/use cards
  - Step 4-5: Optional arbitrage/cashback
- **Why it works**: Explains the stack logic (e.g., "20x points → ~10% base return. Ultimate cards convert to JB Hi-Fi")
- **Arbitrage hints**: When Apple chip + stock signal detected, suggests "Consider Harvey Norman / JB Hi-Fi / Officeworks price match/beat where policy allows"
- **Forward compatibility**: For M4+ chips, adds "Apple silicon generations are forward-compatible for price matching when model/SKU aligns"

---

## Debugging Tips

### Script Fails to Fetch Data
- Check internet connection
- Some sites may be temporarily down (OzBargain, FreePoints, GCDB)
- Timeout is 20 seconds per request

### No Deals Appear
- Keywords list may be too restrictive
- Edit `KEYWORDS` at top of each file to broaden search

### Email Not Sending
- Verify SMTP environment variables are set: `echo $SMTP_HOST`
- Test SMTP credentials separately
- Check Gmail "Less secure app access" or use app-specific password
- Firewall may block port 465 (SMTP_SSL)

### Score Seems Wrong
- Check `score_item()` function in [daily_stack_deal_report.py](daily_stack_deal_report.py#L280-L295)
- Weights can be adjusted:
  - Points multiplier: lines 283-286
  - Gift cards: lines 289-291
  - Merchants: lines 294-295
  - Arbitrage: line 298
  - Cashback: lines 301-303

### HTML Email Looks Broken
- HTML uses inline styles for email client compatibility
- Test in multiple email clients (Gmail, Outlook, Apple Mail)
- Avoid CSS classes/external stylesheets - they don't work in emails

---

## GitHub Actions Testing

The workflow runs daily at 21:00 UTC via [.github/workflows/daily.yml](.github/workflows/daily.yml).

### Manual Trigger

Go to GitHub Actions tab → Select "Daily Deal Report" → Run workflow

### Check Logs

Actions tab → Click on latest run → Expand job steps

### Required Secrets

Set in GitHub repo Settings → Secrets and variables → Actions:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `MAIL_TO`

---

## Common Test Scenarios

### Test Apple Chip Detection
Look for deals with "M1", "M2 Pro", "M4 Max", etc. in titles:
```bash
python daily_deal_report.py --print | grep -i "m[1-4]"
```

### Test Gift Card Stacking
Current promos (as of Jan 2026):
- 20x Everyday Rewards on Ultimate cards at Woolworths (ends Jan 6)
- 20x Flybuys on Apple cards at Coles (ends Jan 6)

These should appear in Top 5 with recipes.

### Test Harvey Norman Integration
Search for deals mentioning Harvey Norman + Apple products + stock/C&C:
```bash
python daily_stack_deal_report.py --print | grep -i "harvey"
```

Should see "Consider Harvey Norman / JB Hi-Fi / Officeworks price match/beat" in arbitrage hints.

### Test Cashback Warnings
Look for deals mentioning ShopBack/TopCashback/Cashrewards:
```bash
python daily_deal_report.py --print | grep -i "shopback"
```

Should see yellow warning: "⚠️ ShopBack typically excludes gift card purchases"

---

## Performance Notes

- First run takes 20-40 seconds (fetches ~50 deals from 3 sources)
- BeautifulSoup parsing is fast (~1-2 seconds total)
- SMTP sending adds 2-5 seconds per email
- GitHub Actions adds ~30 seconds for checkout/setup

---

## Next Steps

1. **Run both scripts in print mode** to see current deals
2. **Set up email** if you want daily automated reports
3. **Adjust keywords** in scripts to match your interests
4. **Tune scoring weights** to prioritize your preferred stack types
5. **Enable GitHub Actions** for hands-off daily emails

