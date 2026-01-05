# Daily Deal Stack Report Agent

## Project Overview
Automated deal aggregator that scrapes Australian deal sites (OzBargain, FreePoints, GCDB) to identify **stackable deals** for maximizing returns through gift cards, points promos, and cashback. Runs daily via GitHub Actions and sends HTML email reports.

## Core Architecture

**Two report generators:**
- `daily_deal_report.py`: Comprehensive keyword-filtered deals across all sources (trending + latest)
- `daily_stack_deal_report.py`: Top 5 high-scoring deals with "why this stack works" explanations

**Data flow:**
1. Fetch HTML from deal sites → 2. Parse with BeautifulSoup → 3. Filter by keywords/merchants → 4. Enrich with stack hints → 5. Generate plain + HTML → 6. Email via SMTP

**Stack scoring algorithm** (`daily_stack_deal_report.py`):
- Points multiplier (20x+ = 8-10 pts, else 4)
- Gift cards (+3), Ultimate/TCN (+3)
- Priority merchants (+2): Officeworks, JB Hi-Fi, The Good Guys, Apple, IKEA
- Cashback mentioned (+2-3)
- Competition/win (-3)

## Critical Patterns

**Keyword filtering is central:**  
Both scripts use `KEYWORDS` list (gift card, cashback, points promos, merchants). `contains_keywords()` runs on all scraped text. Add new terms here for broader matching.

**Merchant detection:**  
`detect_merchants()` scans titles for exact merchant names from `MERCHANTS` list (case-insensitive). Used for categorization and scoring.

**Stack hints = actionable intelligence:**  
`stack_hint()` / `why_stack_works()` functions detect patterns (20x + gift card, Ultimate → JB Hi-Fi conversion) and generate explanations. This is the "why" behind the deal—not scraped, but derived from title analysis.

**HTML email generation:**  
Uses inline CSS for email client compatibility. Nested `<table>` elements (not divs) for layout. `html.escape()` all dynamic content.

## GitHub Actions Workflow

**Schedule:** Daily at 21:00 UTC (`daily.yml`)  
**Secrets required:**
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (email sending)
- `MAIL_TO` (recipient)

**Manual trigger:** `workflow_dispatch` enabled for testing  
**Run order:** `daily_stack_deal_report.py` → `daily_deal_report.py`

## Development Workflow

**Local testing without email:**
```bash
python daily_deal_report.py --print
python daily_stack_deal_report.py --print
```

**Dependencies:** `requests`, `beautifulsoup4`, `lxml` (see `requirements.txt`)

**Web scraping fragility:**  
Fetchers use CSS selectors (`a[href^='/node/']` for OzBargain). If site structure changes, update selectors in `fetch_*()` functions. Timeout is 20s.

## Project-Specific Conventions

- **No classes:** All functions are module-level (functional style)
- **Type hints:** Used in `daily_deal_report.py`, omitted in `daily_stack_deal_report.py` (inconsistent by design)
- **String normalization:** `norm()` collapses whitespace, used before all keyword matching
- **Deduplication:** Track URLs in `seen` set to avoid duplicate deals in report
- **User-Agent:** Custom `DealAgent/1.0` to identify scraper traffic

## When Modifying

**Adding new deal sources:**  
1. Create `fetch_newsource()` returning `list[dict]` with keys: `source`, `title`, `link`
2. Add to `all_items` list in `build_reports()`
3. Update source ranking in `source_rank` dict

**Tuning score weights:**  
Edit `score_item()` in `daily_stack_deal_report.py`. Scores typically 0-20 range.

**Changing email layout:**  
Modify HTML generators in `build_reports()`. Remember: inline styles only, use `<table>` for structure.

**New keywords/merchants:**  
Edit `KEYWORDS` / `MERCHANTS` / `PRIORITY_MERCHANTS` lists at top of files. Changes affect filtering and scoring immediately.
