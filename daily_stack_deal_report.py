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
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple",
    "Amazon", "Woolworths", "Coles", "IKEA"
]

PRIORITY_MERCHANTS = ["Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "IKEA"]

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
        reasons.append("Cashback mentioned, but gift-card payments are often excluded → treat as upside, not core.")

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

    if it.get("cashback"):
        score += 2
        if any(c in ["ShopBack", "TopCashback"] for c in it["cashback"]):
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

# ---------- REPORT ----------
def build_reports():
    today = dt.date.today().isoformat()
    raw = fetch_freepoints() + fetch_gcdb() + fetch_ozb()

    enriched = []
    for it in raw:
        it["merchants"] = detect_merchants(it.get("title", ""))
        it["cashback"] = detect_cashback(it.get("title", ""))
        it["hint"] = stack_hint(it.get("title", ""))
        it["why"] = why_stack_works(it)
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
        if x.get("why"):
            lines.append(f"   Why this stack works: {x['why']}")
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
        why = x.get("why", "")

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
            {f"<div style='margin-top:6px;color:#1f6f43;font-size:12px;'><b>Why this stack works:</b> {esc(why)}</div>" if why else ""}
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