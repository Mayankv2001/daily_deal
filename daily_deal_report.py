#!/usr/bin/env python3
import os
import re
import ssl
import sys
import smtplib
import datetime as dt
from email.message import EmailMessage
import html as html_lib

import requests
from bs4 import BeautifulSoup


# ---------- CONFIG YOU CAN EDIT ----------
KEYWORDS = [
    "gift card", "giftcard", "ultimate", "tcn",
    "shopback", "topcashback", "cashback",
    "flybuys", "everyday rewards", "20x", "10x", "30x",
    "bonus points", "qantas", "velocity",
    "officeworks", "jb hi-fi", "jbhifi", "the good guys", "apple"
]

MERCHANTS = [
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman", "Amazon", "Woolworths", "Coles", "Costco"
]

PHYSICAL_RETAILERS = [
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman", "Bing Lee", "Costco"
]

STOCK_KEYWORDS = [
    "in stock", "click and collect", "c&c", "pick up", "in-store", "in store", "pickup"
]

TIMEOUT = 20
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DealAgent/1.0"


# ---------- HELPERS ----------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def contains_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in KEYWORDS)

def detect_merchants(text: str) -> list[str]:
    t = (text or "").lower()
    found = []
    for m in MERCHANTS:
        if m.lower() in t:
            found.append(m)
    return found

def detect_cashback(text: str) -> list[str]:
    """Detect cashback portals mentioned in text."""
    t = (text or "").lower()
    found = []
    if "shopback" in t:
        found.append("ShopBack")
    if "topcashback" in t:
        found.append("TopCashback")
    if "cashrewards" in t:
        found.append("Cashrewards")
    if "cashback" in t and not found:
        found.append("Cashback")
    return found

def cashback_note(portals: list[str]) -> str | None:
    """Generate conservative cashback warning note."""
    if not portals:
        return None
    portal_str = ", ".join(portals)
    return f"⚠️ {portal_str} typically excludes gift card purchases. Verify portal T&Cs before assuming cashback applies."

def stack_hint(title: str) -> str:
    t = (title or "").lower()
    hints = []
    if ("20x" in t or "10x" in t or "30x" in t) and ("gift" in t and "card" in t):
        hints.append("Likely stack base: points promo on gift cards (~10% back at 20x).")
    if "ultimate" in t and ("woolworths" in t or "big w" in t):
        hints.append("Potential stack: buy Ultimate gift cards on promo → use at JB Hi-Fi/Officeworks (check 1-card-online rule / conversion).")
    if "apple gift" in t and ("coles" in t or "woolworths" in t or "big w" in t):
        hints.append("Potential stack: buy Apple gift cards on promo → pay Apple (can price match) + sometimes cashback (check portal terms).")
    if "cashback" in t or "shopback" in t or "topcashback" in t:
        hints.append("Cashback portals often exclude gift card purchases—verify T&Cs before relying on cashback.")
    if "officeworks" in t or "jb hi-fi" in t:
        hints.append("Check cashback portals: sometimes gift-card payment is allowed, sometimes excluded (read portal T&Cs).")
    return " ".join(hints)

def detect_apple_chip(text: str) -> dict:
    # Examples:
    # detect_apple_chip("MacBook Pro M5 Pro") → {"chip": "M5 Pro", "generation": 5, "tier": "pro"}
    # detect_apple_chip("M6 Ultra") → {"chip": "M6 Ultra", "generation": 6, "tier": "ultra"}
    # detect_apple_chip("Apple M4") → {"chip": "M4", "generation": 4, "tier": "base"}
    # detect_apple_chip("m5") → {"chip": "M5", "generation": 5, "tier": "base"}
    # detect_apple_chip("M3 Max") → {"chip": "M3 Max", "generation": 3, "tier": "max"}
    # detect_apple_chip("no chip") → {"chip": None, "generation": None, "tier": "unknown"}
    
    pattern = r'\bM(\d+)\s*(Pro|Max|Ultra)?\b'
    match = re.search(pattern, text or "", re.IGNORECASE)
    
    if not match:
        return {"chip": None, "generation": None, "tier": "unknown"}
    
    generation = int(match.group(1))
    tier_raw = match.group(2)
    tier = tier_raw.lower() if tier_raw else "base"
    
    # Reconstruct chip name with normalized casing
    chip = f"M{generation}"
    if tier_raw:
        chip += f" {tier_raw.title()}"
    
    return {"chip": chip, "generation": generation, "tier": tier}

def detect_physical_retailer(text: str) -> list[str]:
    """Detect physical retailers that support price match/beat."""
    t = (text or "").lower()
    found = []
    for r in PHYSICAL_RETAILERS:
        if r.lower() in t:
            found.append(r)
    return found

def has_stock_signal(text: str) -> bool:
    """Check if text contains stock/C&C availability signals."""
    t = (text or "").lower()
    return any(kw in t for kw in STOCK_KEYWORDS)

def calculate_confidence(item: dict) -> str:
    """Calculate arbitrage confidence: HIGH/MEDIUM/LOW."""
    title = item.get("title", "")
    chip_info = item.get("chip_info", {})
    physical = item.get("physical_retailers", [])
    has_stock = item.get("has_stock_signal", False)
    
    # Apple chip detected
    if chip_info.get("chip"):
        # High confidence: chip + physical retailer + stock signal
        if physical and has_stock:
            return "HIGH"
        # Low confidence: chip but no physical retailer or stock signal
        if not physical or not has_stock:
            return "LOW"
    
    # Medium confidence for other deals with merchants
    if item.get("merchants"):
        return "MEDIUM"
    
    return "LOW"


# ---------- FETCHERS ----------
def fetch_url(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def fetch_ozbargain_trending(limit: int = 10) -> list[dict]:
    # Try /hot first, fallback to front page
    urls = ["https://www.ozbargain.com.au/hot", "https://www.ozbargain.com.au/"]
    html = None
    for u in urls:
        try:
            html = fetch_url(u)
            break
        except Exception:
            continue
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals = []
    for a in soup.select("a[href^='/node/']"):
        title = norm(a.get_text(" ", strip=True))
        if not title or len(title) < 10:
            continue
        link = "https://www.ozbargain.com.au" + a["href"]
        deals.append({"title": title, "link": link})

    seen = set()
    out = []
    for d in deals:
        if d["link"] in seen:
            continue
        seen.add(d["link"])
        out.append(d)
        if len(out) >= limit:
            break
    return out

def fetch_freepoints_latest(limit: int = 10) -> list[dict]:
    html = fetch_url("https://freepoints.com.au/")
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("a"):
        txt = norm(a.get_text(" ", strip=True))
        href = a.get("href") or ""
        if not href.startswith("https://freepoints.com.au/"):
            continue
        if ("points" in txt.lower() or "gift card" in txt.lower()) and contains_keywords(txt):
            items.append({"source": "FreePoints", "title": txt, "link": href})

    seen = set()
    out = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        out.append(it)
        if len(out) >= limit:
            break
    return out

def fetch_gcdb_latest(limit: int = 10) -> list[dict]:
    html = fetch_url("https://gcdb.com.au/")
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("a"):
        txt = norm(a.get_text(" ", strip=True))
        href = a.get("href") or ""
        if not href.startswith("https://gcdb.com.au/"):
            continue
        if ("gift card" in txt.lower() or "points" in txt.lower() or "off" in txt.lower()) and contains_keywords(txt):
            items.append({"source": "GCDB", "title": txt, "link": href})

    seen = set()
    out = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        out.append(it)
        if len(out) >= limit:
            break
    return out

def fetch_ozbargain_frontpage(limit: int = 20) -> list[dict]:
    html = fetch_url("https://www.ozbargain.com.au/")
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("a[href^='/node/']"):
        href = a.get("href") or ""
        title = norm(a.get_text(" ", strip=True))
        if not title:
            continue
        full = "https://www.ozbargain.com.au" + href
        if contains_keywords(title):
            items.append({"source": "OzBargain", "title": title, "link": full})

    seen = set()
    out = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        out.append(it)
        if len(out) >= limit:
            break
    return out

def fetch_costco_hotbuys() -> list[dict]:
    """Fetch Costco Hot Buys - checks for Apple products.
    Note: Costco uses JavaScript rendering, so we return a manual check reminder."""
    items = []
    
    # Add manual check reminder
    items.append({
        "source": "Costco",
        "title": "🔍 Costco Hot Buys - Manual Check Required (Apple Products, Electronics)",
        "link": "https://www.costco.com.au/c/hot-buys"
    })
    
    # Try to search OzBargain for recent Costco deals as backup
    try:
        html = fetch_url("https://www.ozbargain.com.au/?q=costco")
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href^='/node/']")[:3]:
            title = norm(a.get_text(" ", strip=True))
            if not title or "costco" not in title.lower():
                continue
            link = "https://www.ozbargain.com.au" + a["href"]
            # Only include if it matches keywords (Apple, gift cards, etc.)
            if contains_keywords(title):
                items.append({"source": "Costco (via OzBargain)", "title": title, "link": link})
    except Exception:
        pass
    
    return items


# ---------- REPORT ----------
def build_reports() -> tuple[str, str]:
    today = dt.datetime.now().strftime("%Y-%m-%d")

    trending = fetch_ozbargain_trending(10)

    all_items: list[dict] = []
    all_items += fetch_freepoints_latest(10)
    all_items += fetch_gcdb_latest(10)
    all_items += fetch_ozbargain_frontpage(20)
    all_items += fetch_costco_hotbuys()

    enriched: list[dict] = []
    for it in all_items:
        title = it["title"]
        merch = detect_merchants(title)
        cashback = detect_cashback(title)
        hint = stack_hint(title)
        
        # Apple chip detection and analysis
        chip_info = detect_apple_chip(title)
        physical = detect_physical_retailer(title)
        has_stock = has_stock_signal(title)
        is_apple = chip_info.get("chip") is not None
        
        # Build enriched item
        enriched_item = {
            **it,
            "merchants": merch,
            "cashback": cashback,
            "cashback_note": cashback_note(cashback),
            "hint": hint,
            "chip_info": chip_info,
            "physical_retailers": physical,
            "has_stock_signal": has_stock,
            "is_apple": is_apple,
        }
        
        # Calculate confidence
        confidence = calculate_confidence(enriched_item)
        enriched_item["confidence"] = confidence
        
        # Enhanced hints for Apple chip deals
        if is_apple:
            chip = chip_info.get("chip")
            tier = chip_info.get("tier")
            hints_list = [hint] if hint else []
            
            if physical and has_stock:
                hints_list.append(f"💎 HIGH CONFIDENCE: {chip} deal at physical retailer ({', '.join(physical)}) with stock/C&C. Consider price match/beat at competing stores.")
            elif not physical or not has_stock:
                hints_list.append(f"⚠️ LOW CONFIDENCE: {chip} deal lacks physical retailer or stock/C&C signals. Arbitrage risk high—verify availability before stacking.")
            
            # Tier-specific hints
            if tier in ["pro", "max", "ultra"]:
                hints_list.append(f"Higher-tier chip ({tier.upper()}) detected—premiums typically 20-40% over base. Price match becomes more valuable.")
            
            enriched_item["hint"] = " ".join(hints_list)
        
        # Filter out LOW confidence Apple deals from main list (they'll be shown separately)
        if is_apple and confidence == "LOW":
            enriched_item["excluded_from_main"] = True
        else:
            enriched_item["excluded_from_main"] = False
        
        enriched.append(enriched_item)

    source_rank = {"FreePoints": 0, "GCDB": 1, "OzBargain": 2}
    enriched.sort(key=lambda x: (source_rank.get(x["source"], 9), x["title"].lower()))

    # ----- Plain text -----
    sections: list[str] = []
    sections.append(f"Daily Deal Stack Report — {today}")
    sections.append("Focus keywords: " + ", ".join(KEYWORDS))
    sections.append("")

    for src in ["FreePoints", "GCDB", "OzBargain", "Costco", "Costco (via OzBargain)"]:
        src_items = [x for x in enriched if x["source"] == src and not x.get("excluded_from_main")]
        if not src_items:
            continue
        sections.append(f"=== {src} (top {len(src_items)}) ===")
        for i, x in enumerate(src_items, 1):
            merch_txt = f" | Merchants: {', '.join(x['merchants'])}" if x.get("merchants") else ""
            cashback_txt = f" | Cashback: {', '.join(x['cashback'])}" if x.get("cashback") else ""
            
            # Add chip info if detected
            chip_info = x.get("chip_info", {})
            chip_txt = ""
            if chip_info.get("chip"):
                chip = chip_info["chip"]
                conf = x.get("confidence", "UNKNOWN")
                chip_txt = f" | Apple Chip: {chip} | Confidence: {conf}"
            
            hint_txt = f"\n    Stack hint: {x['hint']}" if x.get("hint") else ""
            cashback_note_txt = f"\n    {x['cashback_note']}" if x.get("cashback_note") else ""
            sections.append(f"{i}. {x['title']}{merch_txt}{cashback_txt}{chip_txt}\n    {x['link']}{hint_txt}{cashback_note_txt}")
        sections.append("")
    
    # Show excluded low-confidence Apple deals separately
    excluded = [x for x in enriched if x.get("excluded_from_main")]
    if excluded:
        sections.append("=== ⚠️ Low Confidence Apple Deals (Excluded from Main List) ===")
        sections.append("These deals lack physical retailer or stock/C&C signals.")
        sections.append("")
        for i, x in enumerate(excluded, 1):
            chip = x.get("chip_info", {}).get("chip", "Unknown")
            sections.append(f"{i}. {x['title']} | Chip: {chip}\n    {x['link']}")
        sections.append("")

    sections.append("🔥 OzBargain Trending (Top 10)")
    sections.append("Hot deals right now (from /hot).")
    sections.append("")
    if trending:
        for i, d in enumerate(trending, 1):
            sections.append(f"{i}. {d['title']}\n    {d['link']}")
    else:
        sections.append("No trending deals found today.")
    sections.append("")

    sections.append("=== Quick stacking playbook ===")
    sections.append(
        "1) Start with points promo on gift cards (e.g., 20x) → base return.\n"
        "2) Use the correct gift card type at the target merchant (Ultimate/TCN vs Apple-only).\n"
        "3) If buying online via cashback portal, confirm portal terms allow gift-card/account-balance payments.\n"
        "4) If portal excludes gift-card payments, you still keep the base points return.\n"
    )

    plain = "\n".join(sections)

    # ----- HTML -----
    def esc(s: str) -> str:
        return html_lib.escape(s or "")

    def card(title: str, subtitle: str, inner_html: str) -> str:
        sub = f"<div style='color:#666;font-size:12px;margin-top:4px;'>{esc(subtitle)}</div>" if subtitle else ""
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:14px;margin:14px 0;background:#fff;">
          <tr><td style="padding:14px 14px 10px 14px;">
            <div style="font-size:16px;font-weight:700;">{esc(title)}</div>{sub}
          </td></tr>
          <tr><td style="padding:0 10px 12px 10px;">{inner_html}</td></tr>
        </table>
        """

    def deal_table(rows_html: str) -> str:
        if not rows_html:
            rows_html = "<tr><td style='padding:10px;color:#666;'>No items found.</td></tr>"
        return f"<table width='100%' cellpadding='0' cellspacing='0' style='border-collapse:collapse;'>{rows_html}</table>"

    def row(idx: int, title: str, link: str, meta: str = "", hint: str = "") -> str:
        meta_html = f"<div style='margin-top:4px;color:#555;font-size:12px;'>{esc(meta)}</div>" if meta else ""
        hint_html = f"<div style='margin-top:6px;color:#333;font-size:12px;'><b>Stack hint:</b> {esc(hint)}</div>" if hint else ""
        return f"""
        <tr>
          <td style="padding:10px 6px;border-top:1px solid #eee;vertical-align:top;width:34px;color:#666;">{idx}.</td>
          <td style="padding:10px 6px;border-top:1px solid #eee;vertical-align:top;">
            <div style="font-size:14px;line-height:20px;">
              <a href="{esc(link)}" style="color:#1155cc;text-decoration:none;">{esc(title)}</a>
            </div>
            {meta_html}
            {hint_html}
          </td>
        </tr>
        """

    html_sections = []
    kw_preview = ", ".join(KEYWORDS[:10]) + ("…" if len(KEYWORDS) > 10 else "")
    html_sections.append(f"""
    <div style="padding:14px 16px;border:1px solid #eee;border-radius:14px;background:#fff;">
      <div style="font-size:18px;font-weight:800;">Daily Deal Stack Report</div>
      <div style="margin-top:6px;color:#666;font-size:13px;">{esc(today)}</div>
      <div style="margin-top:8px;color:#666;font-size:12px;">Keywords: {esc(kw_preview)}</div>
    </div>
    """)

    for src in ["FreePoints", "GCDB", "OzBargain", "Costco", "Costco (via OzBargain)"]:
        src_items = [x for x in enriched if x["source"] == src and not x.get("excluded_from_main")]
        rows = ""
        for i, x in enumerate(src_items, 1):
            meta_parts = []
            if x.get("merchants"):
                meta_parts.append("Merchants: " + ", ".join(x["merchants"]))
            if x.get("cashback"):
                meta_parts.append("Cashback: " + ", ".join(x["cashback"]))
            
            # Add chip info with confidence badge
            chip_info = x.get("chip_info", {})
            if chip_info.get("chip"):
                conf = x.get("confidence", "UNKNOWN")
                badge_color = {"HIGH": "#28a745", "MEDIUM": "#ffc107", "LOW": "#dc3545"}.get(conf, "#6c757d")
                meta_parts.append(f"<span style='background:{badge_color};color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:700;'>{conf}</span> Apple Chip: {esc(chip_info['chip'])}")
            
            meta = " | ".join(meta_parts)
            
            # Build hint with cashback note
            hint_parts = []
            if x.get("hint"):
                hint_parts.append(x["hint"])
            if x.get("cashback_note"):
                hint_parts.append(f"<div style='margin-top:6px;padding:6px 8px;background:#fff3cd;border-left:3px solid #ffc107;border-radius:3px;color:#856404;font-size:11px;'>{esc(x['cashback_note'])}</div>")
            combined_hint = "<br>".join(hint_parts) if hint_parts else x.get("hint", "")
            
            rows += row(i, x["title"], x["link"], meta=meta, hint=combined_hint)
        html_sections.append(card(src, f"Top {len(src_items)} items", deal_table(rows)))
    
    # Show excluded low-confidence Apple deals
    excluded = [x for x in enriched if x.get("excluded_from_main")]
    if excluded:
        rows = ""
        for i, x in enumerate(excluded, 1):
            chip = x.get("chip_info", {}).get("chip", "Unknown")
            meta = f"<span style='background:#dc3545;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:700;'>LOW</span> Apple Chip: {esc(chip)}"
            rows += row(i, x["title"], x["link"], meta=meta, hint=x.get("hint", ""))
        html_sections.append(card("⚠️ Low Confidence Apple Deals", "Excluded from main list—lack physical retailer or stock/C&C signals", deal_table(rows)))

    rows = ""
    for i, d in enumerate(trending[:10], 1):
        rows += row(i, d["title"], d["link"])
    html_sections.append(card("🔥 OzBargain Trending", "Hot deals right now (/hot)", deal_table(rows)))

    playbook = """
    <ol style="margin:10px 0 0 18px;color:#333;font-size:13px;line-height:18px;">
      <li>Start with points promo on gift cards (e.g., 20x) → base return.</li>
      <li>Use the correct gift card type at the target merchant (Ultimate/TCN vs Apple-only).</li>
      <li>If buying online via cashback portal, confirm portal terms allow gift-card/account-balance payments.</li>
      <li>If portal excludes gift-card payments, you still keep the base points return.</li>
    </ol>
    """
    html_sections.append(card("🧠 Quick stacking playbook", "", playbook))

    html_doc = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7f9;font-family:Arial,Helvetica,sans-serif;">
    <div style="max-width:760px;margin:0 auto;padding:18px;">
      {''.join(html_sections)}
      <div style="color:#999;font-size:11px;margin-top:10px;">Sent by your Deal Agent.</div>
    </div>
  </body>
</html>"""

    return plain, html_doc


# ---------- EMAIL ----------
def send_email(subject: str, body: str, html_body: str | None = None):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    mail_to = os.environ.get("MAIL_TO")

    smtp_pass = (smtp_pass or "").replace("\xa0", "")
    smtp_pass = "".join(smtp_pass.split())

    missing = [k for k, v in {
        "SMTP_HOST": smtp_host,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "MAIL_TO": mail_to,
    }.items() if not v]

    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = mail_to
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as s:
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def main():
    plain, html_doc = build_reports()
    subject = "Daily Deal Stack Report"

    if "--print" in sys.argv:
        print(plain)
        return

    send_email(subject, plain, html_doc)
    print("✅ Sent daily report email.")


if __name__ == "__main__":
    main()