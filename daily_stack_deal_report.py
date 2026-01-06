#!/usr/bin/env python3
import os, re, sys, smtplib, datetime as dt
from email.message import EmailMessage
import html as html_lib

import requests
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
KEYWORDS = [
    "gift card", "giftcard", "ultimate", "tcn",
    "shopback", "topcashback", "cashback",
    "flybuys", "everyday rewards", "20x", "10x", "30x",
    "bonus points", "qantas", "velocity",
    "officeworks", "jb hi-fi", "jbhifi", "the good guys", "apple"
]

MERCHANTS = [
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman",
    "Amazon", "Woolworths", "Coles", "IKEA", "Costco"
]

PRIORITY_MERCHANTS = ["Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman", "IKEA", "Costco"]

PHYSICAL_RETAILERS = {
    "Officeworks": ["JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "JB Hi-Fi": ["Officeworks", "The Good Guys", "Harvey Norman"],
    "The Good Goods": ["Officeworks", "JB Hi-Fi", "Harvey Norman"],
    "Apple": ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "Harvey Norman": ["Officeworks", "JB Hi-Fi", "The Good Guys"],
    "Costco": ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"],
}

STOCK_KEYWORDS = [
    "in stock", "click and collect", "c&c", "click & collect",
    "pick up", "pickup", "in-store", "in store", "store stock"
]

LATEST_KNOWN_GENERATION = 4  # M4 as of Jan 2026

TIMEOUT = 20
UA = "Mozilla/5.0 DealAgent/1.0"

# ---------- HELPERS ----------
def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def contains_keywords(text):
    t = (text or "").lower()
    return any(k in t for k in KEYWORDS)

def detect_merchants(text):
    t = (text or "").lower()
    return [m for m in MERCHANTS if m.lower() in t]

def detect_cashback(text):
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

def generate_cashback_note(portals):
    """Generate conservative cashback warning note."""
    if not portals:
        return None
    portal_str = ", ".join(portals)
    return f"⚠️ {portal_str} typically excludes gift card purchases. Verify portal T&Cs before assuming cashback applies."

def extract_x(text):
    m = re.search(r"(\d{1,3})\s*x\b", (text or "").lower())
    return int(m.group(1)) if m else None

def stack_hint(title):
    t = (title or "").lower()
    hints = []
    if extract_x(title) and "gift" in t:
        hints.append("Points promo on gift cards → strong base return.")
    if "ultimate" in t or "tcn" in t:
        hints.append("Multi-retailer gift card → JB / OW / TGG stackable.")
    if any(k in t for k in ["officeworks", "jb hi-fi", "jbhifi"]):
        hints.append("Check cashback portal T&Cs for gift card payments.")
    return " ".join(hints)

def detect_apple_chip(text):
    """Detect Apple Silicon chip from text."""
    pattern = r'\bM(\d+)\s*(Pro|Max|Ultra)?\b'
    match = re.search(pattern, text or "", re.IGNORECASE)
    
    if not match:
        return {"chip": None, "generation": None, "tier": "unknown"}
    
    generation = int(match.group(1))
    tier_raw = match.group(2)
    tier = tier_raw.lower() if tier_raw else "base"
    
    chip = f"M{generation}"
    if tier_raw:
        chip += f" {tier_raw.title()}"
    
    return {"chip": chip, "generation": generation, "tier": tier}

def detect_physical_retailers(text):
    """Detect physical retailers that support price match/beat."""
    t = (text or "").lower()
    found = []
    for retailer in PHYSICAL_RETAILERS.keys():
        if retailer.lower() in t:
            found.append(retailer)
    return found

def detect_stock_signal(text):
    """Check if text contains stock/C&C availability signals."""
    t = (text or "").lower()
    return any(kw in t for kw in STOCK_KEYWORDS)

def calculate_arbitrage(item):
    """Calculate arbitrage opportunity: eligible, targets, confidence."""
    title = item.get("title", "")
    physical = detect_physical_retailers(title)
    has_stock = detect_stock_signal(title)
    chip_info = item.get("chip_info", {})
    
    # Not eligible if no physical retailer mentioned
    if not physical:
        return {"eligible": False, "targets": [], "confidence": "none"}
    
    # Build list of potential arbitrage targets
    targets = []
    for retailer in physical:
        if retailer in PHYSICAL_RETAILERS:
            targets.extend(PHYSICAL_RETAILERS[retailer])
    
    # Remove duplicates
    targets = list(set(targets))
    
    # Determine confidence level
    confidence = "none"
    if targets:
        # High confidence: physical retailer + stock signal + (Apple chip OR priority merchant)
        if has_stock and (chip_info.get("chip") or any(m in PRIORITY_MERCHANTS for m in physical)):
            confidence = "high"
        # Medium confidence: physical retailer + stock signal
        elif has_stock:
            confidence = "medium"
        # Low confidence: physical retailer mentioned but no stock signal
        else:
            confidence = "low"
    
    return {
        "eligible": len(targets) > 0,
        "targets": targets,
        "confidence": confidence
    }

def detect_gift_card_type(text):
    """Detect gift card type: apple, ultimate, tcn, or generic."""
    t = (text or "").lower()
    if "apple gift" in t or "apple giftcard" in t:
        return "apple"
    if "ultimate" in t:
        return "ultimate"
    if "tcn" in t:
        return "tcn"
    if "gift card" in t or "giftcard" in t:
        return "generic"
    return None

def generate_stack_recipe(item):
    """Generate 3-5 step recipe for stacking this deal."""
    title = item.get("title", "")
    t = title.lower()
    gc_type = detect_gift_card_type(title)
    x = extract_x(title)
    merchants = item.get("merchants", [])
    arbitrage = item.get("arbitrage", {})
    chip_info = item.get("chip_info", {})
    
    steps = []
    
    # Step 1: Points promo
    if x:
        if x >= 20:
            steps.append(f"Activate {x}x points in your loyalty account before purchase.")
        else:
            steps.append(f"Ensure {x}x points promo is active in your account.")
    
    # Step 2: Gift card purchase
    if gc_type == "ultimate":
        steps.append("Buy Ultimate gift cards at promoted merchant (front-load points return).")
        steps.append("Convert Ultimate cards online to JB Hi-Fi/Officeworks denominations (check 1-card-online.com.au limits).")
    elif gc_type == "tcn":
        steps.append("Buy TCN gift cards to use at category merchants (check specific merchant list).")
    elif gc_type == "apple":
        steps.append("Buy Apple gift cards at promoted merchant (front-load points return).")
        steps.append("Use Apple gift cards for Apple Store purchases (online or in-store, check online gift card limits).")
    elif gc_type == "generic":
        steps.append("Buy gift cards at promoted merchant (front-load points return).")
        if merchants:
            steps.append(f"Use gift cards at {merchants[0]} (check online gift card limits).")
    
    # Step 3: Arbitrage opportunity
    if arbitrage.get("eligible") and arbitrage.get("confidence") in ["high", "medium"]:
        targets = arbitrage.get("targets", [])
        if targets and chip_info.get("chip"):
            steps.append(f"Compare prices at {', '.join(targets[:2])} for price match/beat opportunities (verify current policies).")
        elif targets:
            steps.append(f"Check {', '.join(targets[:2])} for competitive pricing (price match may be available).")
    
    # Step 4: Cashback (optional)
    if item.get("cashback"):
        cashback_sites = ", ".join(item["cashback"][:2])
        steps.append(f"Optional: Use {cashback_sites} if portal allows gift-card/account-balance payments (check T&Cs).")
    
    # Step 5: Generic caution
    if gc_type in ["ultimate", "apple"] or (gc_type and any(m in merchants for m in ["JB Hi-Fi", "Officeworks", "Apple"])):
        if "check online gift card limits" not in " ".join(steps):
            steps.append("Check online gift card limits at redemption merchant.")
    
    # Return max 5 steps
    return steps[:5]

def why_stack_works(it):
    """
    High-signal explanation of why this deal stacks TODAY.
    ✅ No scraping, no fragile assumptions.
    """
    t = (it.get("title") or "").lower()
    reasons = []

    x = extract_x(it.get("title", ""))
    if x:
        if x >= 20:
            reasons.append(f"{x}x points promo → ~{x//2}% base return.")
        else:
            reasons.append(f"{x}x points promo → meaningful base return.")

    if "gift card" in t or "giftcard" in t:
        reasons.append("Buying gift cards front-loads rewards before purchase.")

    if "ultimate" in t:
        reasons.append("Ultimate gift cards can be converted to JB Hi-Fi / Officeworks.")
    if "tcn" in t:
        reasons.append("TCN cards work across multiple merchants (category-based).")
    if "apple gift" in t:
        reasons.append("Apple gift cards can pay Apple directly (and often stack with price match).")

    if any(m in it.get("merchants", []) for m in ["JB Hi-Fi", "Officeworks", "The Good Guys", "IKEA"]):
        reasons.append("Target merchant accepts gift cards (online limits may apply).")

    if it.get("cashback"):
        reasons.append("Cashback portals often exclude gift card purchases—verify T&Cs before relying on cashback.")
    
    # Apple chip forward-compatibility for price matching
    chip_info = it.get("chip_info", {})
    if chip_info.get("chip") and chip_info.get("generation", 0) >= LATEST_KNOWN_GENERATION:
        reasons.append("Apple silicon generations are forward-compatible for price matching when model/SKU aligns.")
    
    # Apple chip with stock signal - specific price match hint
    if chip_info.get("chip"):
        # Check for stock/C&C signals in title
        title_lower = (it.get("title", "")).lower()
        has_stock = any(kw in title_lower for kw in STOCK_KEYWORDS)
        if has_stock:
            reasons.append("Consider Harvey Norman / JB Hi-Fi / Officeworks price match/beat where policy allows.")
    
    # Physical retailer arbitrage opportunity
    arbitrage = it.get("arbitrage", {})
    if arbitrage.get("eligible") and arbitrage.get("confidence") in ["high", "medium"]:
        targets = arbitrage.get("targets", [])
        if targets:
            target_str = ", ".join(targets[:2])  # Show max 2 targets
            if arbitrage["confidence"] == "high":
                reasons.append(f"Physical stock signals suggest possible price match arbitrage at {target_str} (verify current policies).")
            else:
                reasons.append(f"Physical retailer deal may enable price comparison with {target_str} (check stock and policies).")

    return " ".join(reasons)

def score_item(it):
    score = 0
    t = (it.get("title") or "").lower()

    x = extract_x(it.get("title", ""))
    if x:
        score += 10 if x >= 30 else 8 if x >= 20 else 4

    if "gift card" in t or "giftcard" in t:
        score += 3
    if "ultimate" in t or "tcn" in t:
        score += 3
    if any(m in it.get("merchants", []) for m in PRIORITY_MERCHANTS):
        score += 2

    # Cashback: reduced weight, never outweighs points/gift cards
    if it.get("cashback"):
        score += 1  # Reduced from 2 to 1
        if any(c in ["ShopBack", "TopCashback"] for c in it["cashback"]):
            score += 0.5  # Reduced from 1 to 0.5
    
    # Arbitrage opportunity scoring
    arbitrage = it.get("arbitrage", {})
    if arbitrage.get("eligible"):
        confidence = arbitrage.get("confidence", "none")
        if confidence == "high":
            score += 4
        elif confidence == "medium":
            score += 2
        elif confidence == "low":
            score += 1

    if "win " in t or "competition" in t:
        score -= 3

    return round(score, 1)

# ---------- FETCHERS ----------
def fetch_url(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def fetch_freepoints():
    soup = BeautifulSoup(fetch_url("https://freepoints.com.au/"), "lxml")
    out = []
    for a in soup.select("a[href^='https://freepoints.com.au/']"):
        t = norm(a.get_text(" ", strip=True))
        if t and contains_keywords(t):
            out.append({"source": "FreePoints", "title": t, "link": a["href"]})
    return out[:15]

def fetch_gcdb():
    soup = BeautifulSoup(fetch_url("https://gcdb.com.au/"), "lxml")
    out = []
    for a in soup.select("a[href^='https://gcdb.com.au/']"):
        t = norm(a.get_text(" ", strip=True))
        if t and contains_keywords(t):
            out.append({"source": "GCDB", "title": t, "link": a["href"]})
    return out[:15]

def fetch_ozb():
    soup = BeautifulSoup(fetch_url("https://www.ozbargain.com.au/"), "lxml")
    out = []
    for a in soup.select("a[href^='/node/']"):
        t = norm(a.get_text(" ", strip=True))
        if t and contains_keywords(t):
            out.append({
                "source": "OzBargain",
                "title": t,
                "link": "https://www.ozbargain.com.au" + a["href"]
            })
    return out[:20]

def fetch_costco():
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
def build_reports():
    today = dt.date.today().isoformat()
    raw = fetch_freepoints() + fetch_gcdb() + fetch_ozb() + fetch_costco()

    enriched = []
    for it in raw:
        it["merchants"] = detect_merchants(it.get("title", ""))
        it["cashback"] = detect_cashback(it.get("title", ""))
        it["cashback_note"] = generate_cashback_note(it["cashback"])
        it["hint"] = stack_hint(it.get("title", ""))
        it["chip_info"] = detect_apple_chip(it.get("title", ""))
        it["arbitrage"] = calculate_arbitrage(it)
        it["why"] = why_stack_works(it)
        it["recipe"] = generate_stack_recipe(it)
        it["score"] = score_item(it)
        enriched.append(it)

    best = sorted(enriched, key=lambda x: x.get("score", 0), reverse=True)[:5]

    # ----- PLAIN TEXT -----
    lines = [f"🏆 Best Stacks Today — {today}", ""]
    for i, x in enumerate(best, 1):
        cb = f" | Cashback: {', '.join(x['cashback'])}" if x.get("cashback") else ""
        lines.append(f"{i}. [{x['score']}] {x['title']}")
        lines.append(f"   Merchants: {', '.join(x.get('merchants', []))}{cb}")
        lines.append(f"   {x['link']}")
        if x.get("hint"):
            lines.append(f"   Hint: {x['hint']}")
        if x.get("cashback_note"):
            lines.append(f"   {x['cashback_note']}")
        if x.get("why"):
            lines.append(f"   Why this stack works: {x['why']}")
        if x.get("recipe"):
            lines.append(f"   📋 Stack Recipe:")
            for step_num, step in enumerate(x["recipe"], 1):
                lines.append(f"      {step_num}. {step}")
        lines.append("")

    plain = "\n".join(lines)

    # ----- HTML -----
    def esc(s):
        return html_lib.escape(s or "")

    rows = ""
    for i, x in enumerate(best, 1):
        merchants = ", ".join(x.get("merchants", []))
        cashback = ", ".join(x.get("cashback", []))
        hint = x.get("hint", "")
        cashback_note = x.get("cashback_note", "")
        why = x.get("why", "")
        recipe = x.get("recipe", [])
        
        # Build recipe HTML
        recipe_html = ""
        if recipe:
            recipe_steps = "".join([f"<li style='margin:3px 0;'>{esc(step)}</li>" for step in recipe])
            recipe_html = f"""
            <div style='margin-top:8px;padding:8px;background:#f0f8ff;border-left:3px solid #4a90e2;border-radius:4px;'>
              <div style='font-weight:700;color:#2c5aa0;font-size:12px;margin-bottom:4px;'>📋 Stack Recipe:</div>
              <ol style='margin:4px 0 0 18px;padding:0;color:#333;font-size:11px;line-height:16px;'>
                {recipe_steps}
              </ol>
            </div>
            """

        rows += f"""
        <tr>
          <td style="padding:8px 10px;vertical-align:top;color:#666;">{i}.</td>
          <td style="padding:8px 10px;">
            <div style="font-size:14px;line-height:20px;">
              <b>[{esc(str(x.get('score', '')))}]</b>
              <a href="{esc(x.get('link',''))}">{esc(x.get('title',''))}</a>
            </div>
            <div style="margin-top:4px;color:#555;font-size:12px;">
              Merchants: {esc(merchants)}
              {f"<br>Cashback: {esc(cashback)}" if cashback else ""}
            </div>
            {f"<div style='margin-top:6px;color:#333;font-size:12px;'><b>Hint:</b> {esc(hint)}</div>" if hint else ""}
            {f"<div style='margin-top:6px;padding:6px 8px;background:#fff3cd;border-left:3px solid #ffc107;border-radius:3px;color:#856404;font-size:11px;'>{esc(cashback_note)}</div>" if cashback_note else ""}
            {f"<div style='margin-top:6px;color:#1f6f43;font-size:12px;'><b>Why this stack works:</b> {esc(why)}</div>" if why else ""}
            {recipe_html}
          </td>
        </tr>
        """

    html = f"""
    <html>
      <body style="font-family:Arial;background:#f6f7f9;padding:16px;">
        <div style="max-width:760px;margin:0 auto;background:#fff;border:1px solid #eee;border-radius:14px;padding:14px;">
          <h2 style="margin:0 0 10px 0;">🏆 Best Stacks Today — {esc(today)}</h2>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
            {rows}
          </table>
        </div>
      </body>
    </html>
    """

    return plain, html

# ---------- EMAIL ----------
def send_email(subject, body, html_body):
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)

def main():
    plain, html = build_reports()
    if "--print" in sys.argv:
        print(plain)
        return
    send_email("Best Stack Deals Today", plain, html)
    print("✅ Sent")

if __name__ == "__main__":
    main()