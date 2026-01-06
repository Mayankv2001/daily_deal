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
    "The Good Guys": ["Officeworks", "JB Hi-Fi", "Harvey Norman"],
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
        score += 1
        if any(c in ["ShopBack", "TopCashback"] for c in it["cashback"]):
            score += 0.5
    
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

# ---------- FETCHERS ----------
def fetch_ozbargain_trending(limit=10):
    """Fetch trending deals from OzBargain /hot page."""
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

def fetch_freepoints_latest(limit=10):
    """Fetch latest deals from FreePoints."""
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

def fetch_gcdb_latest(limit=10):
    """Fetch latest deals from GCDB."""
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

def fetch_ozbargain_frontpage(limit=20):
    """Fetch deals from OzBargain front page."""
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

def fetch_costco_hotbuys():
    """Fetch Costco Hot Buys - checks for Apple products only."""
    items = []
    
    # Add manual check reminder
    items.append({
        "source": "Costco",
        "title": "🔍 Costco Hot Buys - Manual Check Required (Apple Products Only)",
        "link": "https://www.costco.com.au/c/hot-buys"
    })
    
    # Try to search OzBargain for recent Costco Apple deals as backup
    try:
        html = fetch_url("https://www.ozbargain.com.au/?q=costco+apple")
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href^='/node/']")[:5]:
            title = norm(a.get_text(" ", strip=True))
            if not title or "costco" not in title.lower():
                continue
            # Only include Apple products, exclude gift cards
            title_lower = title.lower()
            if "apple" in title_lower and "gift" not in title_lower and "giftcard" not in title_lower:
                link = "https://www.ozbargain.com.au" + a["href"]
                items.append({"source": "Costco (via OzBargain)", "title": title, "link": link})
    except Exception:
        pass
    
    return items

# ---------- ADDITIONAL HELPER FOR DAILY REPORT ----------
def calculate_confidence(item):
    """Calculate arbitrage confidence: HIGH/MEDIUM/LOW (for daily report)."""
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

# ---------- STACK REPORT ----------
def build_stack_report() -> tuple[str, str]:
    """
    Build Top 5 Stack Report.
    Returns: (plain_text, html)
    """
    today = dt.date.today().isoformat()
    raw = fetch_freepoints_latest(15) + fetch_gcdb_latest(15) + fetch_ozbargain_frontpage(20) + fetch_costco_hotbuys()

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
    <div style="margin:20px 0;padding:16px;border:2px solid #4a90e2;border-radius:8px;background:#f0f8ff;">
      <h2 style="margin:0 0 10px 0;color:#2c5aa0;">🏆 Best Stacks Today — {esc(today)}</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;background:#fff;border-radius:6px;">
        {rows}
      </table>
    </div>
    """
    
    return plain, html


def build_daily_report() -> tuple[str, str]:
    """
    Build comprehensive Daily Deal Report.
    Returns: (plain_text, html)
    """
    today = dt.datetime.now().strftime("%Y-%m-%d")
    
    trending = fetch_ozbargain_trending(10)

    all_items = []
    all_items += fetch_freepoints_latest(10)
    all_items += fetch_gcdb_latest(10)
    all_items += fetch_ozbargain_frontpage(20)
    all_items += fetch_costco_hotbuys()

    enriched = []
    for it in all_items:
        title = it["title"]
        merch = detect_merchants(title)
        cashback = detect_cashback(title)
        hint = stack_hint(title)
        
        # Apple chip detection and analysis
        chip_info = detect_apple_chip(title)
        physical = detect_physical_retailers(title)
        has_stock = detect_stock_signal(title)
        is_apple = chip_info.get("chip") is not None
        
        # Build enriched item
        enriched_item = {
            **it,
            "merchants": merch,
            "cashback": cashback,
            "cashback_note": generate_cashback_note(cashback),
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
    sections = []
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
    def esc(s):
        return html_lib.escape(s or "")

    def card(title, subtitle, inner_html):
        sub = f"<div style='color:#666;font-size:12px;margin-top:4px;'>{esc(subtitle)}</div>" if subtitle else ""
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:14px;margin:14px 0;background:#fff;">
          <tr><td style="padding:14px 14px 10px 14px;">
            <div style="font-size:16px;font-weight:700;">{esc(title)}</div>{sub}
          </td></tr>
          <tr><td style="padding:0 10px 12px 10px;">{inner_html}</td></tr>
        </table>
        """

    def deal_table(rows_html):
        if not rows_html:
            rows_html = "<tr><td style='padding:10px;color:#666;'>No items found.</td></tr>"
        return f"<table width='100%' cellpadding='0' cellspacing='0' style='border-collapse:collapse;'>{rows_html}</table>"

    def row(idx, title, link, meta="", hint=""):
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


def build_combined_report() -> tuple[str, str]:
    """
    Build combined report with both stack and daily reports.
    Returns: (plain_text, html)
    """
    today = dt.datetime.now().strftime("%Y-%m-%d")
    
    # Build both reports with error handling
    stack_plain = None
    stack_html = None
    stack_error = None
    try:
        stack_plain, stack_html = build_stack_report()
    except Exception as e:
        stack_error = str(e)
        stack_plain = f"⚠️ Stack report failed: {stack_error}"
        stack_html = f"""
        <div style="margin:20px 0;padding:16px;border:2px solid #dc3545;border-radius:8px;background:#f8d7da;">
          <h2 style="margin:0 0 10px 0;color:#721c24;">⚠️ Stack Report Failed</h2>
          <p style="margin:0;color:#721c24;">Error: {html_lib.escape(stack_error)}</p>
        </div>
        """
    
    daily_plain = None
    daily_html = None
    daily_body = None
    daily_error = None
    try:
        daily_plain, daily_html = build_daily_report()
        # Extract body content from daily HTML (it returns a complete document)
        import re as re_module
        daily_body_match = re_module.search(r'<body[^>]*>(.*?)</body>', daily_html, re_module.DOTALL)
        if daily_body_match:
            daily_body = daily_body_match.group(1)
        else:
            daily_body = daily_html  # fallback if no body tags found
    except Exception as e:
        daily_error = str(e)
        daily_plain = f"⚠️ Daily report failed: {daily_error}"
        daily_body = f"""
        <div style="margin:20px 0;padding:16px;border:2px solid #dc3545;border-radius:8px;background:#f8d7da;">
          <h2 style="margin:0 0 10px 0;color:#721c24;">⚠️ Daily Report Failed</h2>
          <p style="margin:0;color:#721c24;">Error: {html_lib.escape(daily_error)}</p>
        </div>
        """
    
    # Combine plain text
    plain_sections = [
        "=" * 80,
        f"COMBINED DEAL REPORT — {today}",
        "=" * 80,
        "",
        stack_plain,
        "",
        "=" * 80,
        "",
        daily_plain,
        "",
        "=" * 80,
        "Generated by Daily Deal Agent",
        ""
    ]
    plain = "\n".join(plain_sections)
    
    # Combine HTML
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
  </head>
  <body style="margin:0;padding:0;background:#f6f7f9;font-family:Arial,Helvetica,sans-serif;">
    <div style="max-width:800px;margin:0 auto;padding:20px;">
      
      <!-- Header -->
      <div style="text-align:center;padding:20px;background:#fff;border:1px solid #ddd;border-radius:8px;margin-bottom:20px;">
        <h1 style="margin:0;color:#333;">Combined Deal Report</h1>
        <p style="margin:8px 0 0 0;color:#666;">{today}</p>
      </div>
      
      <!-- Stack Report Section -->
      {stack_html}
      
      <!-- Daily Report Section -->
      {daily_body}
      
      <!-- Footer -->
      <div style="margin-top:30px;padding:16px;text-align:center;color:#999;font-size:11px;border-top:1px solid #ddd;">
        Generated by Daily Deal Agent
      </div>
      
    </div>
  </body>
</html>"""
    
    return plain, html


def send_email(subject: str, body: str, html_body: str | None = None):
    """Send email via SMTP."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    mail_to = os.environ.get("MAIL_TO")

    # Clean password
    smtp_pass = (smtp_pass or "").replace("\xa0", "")
    smtp_pass = "".join(smtp_pass.split())

    # Validate required env vars
    missing = [k for k, v in {
        "SMTP_HOST": smtp_host,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "MAIL_TO": mail_to,
    }.items() if not v]

    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    # Build message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = mail_to
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    # Send
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as s:
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def main():
    """Main entry point."""
    plain, html = build_combined_report()
    subject = "Combined Daily Deal Report"

    if "--print" in sys.argv:
        print(plain)
        return

    send_email(subject, plain, html)
    print("✅ Sent combined report email.")


if __name__ == "__main__":
    main()
