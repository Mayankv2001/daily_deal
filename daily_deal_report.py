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
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Amazon", "Woolworths", "Coles"
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

def stack_hint(title: str) -> str:
    t = (title or "").lower()
    hints = []
    if ("20x" in t or "10x" in t or "30x" in t) and ("gift" in t and "card" in t):
        hints.append("Likely stack base: points promo on gift cards (~10% back at 20x).")
    if "ultimate" in t and ("woolworths" in t or "big w" in t):
        hints.append("Potential stack: buy Ultimate gift cards on promo → use at JB Hi-Fi/Officeworks (check 1-card-online rule / conversion).")
    if "apple gift" in t and ("coles" in t or "woolworths" in t or "big w" in t):
        hints.append("Potential stack: buy Apple gift cards on promo → pay Apple (can price match) + sometimes cashback (check portal terms).")
    if "officeworks" in t or "jb hi-fi" in t:
        hints.append("Check cashback portals: sometimes gift-card payment is allowed, sometimes excluded (read portal T&Cs).")
    return " ".join(hints)


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


# ---------- REPORT ----------
def build_reports() -> tuple[str, str]:
    today = dt.datetime.now().strftime("%Y-%m-%d")

    trending = fetch_ozbargain_trending(10)

    all_items: list[dict] = []
    all_items += fetch_freepoints_latest(10)
    all_items += fetch_gcdb_latest(10)
    all_items += fetch_ozbargain_frontpage(20)

    enriched: list[dict] = []
    for it in all_items:
        merch = detect_merchants(it["title"])
        hint = stack_hint(it["title"])
        enriched.append({**it, "merchants": merch, "hint": hint})

    source_rank = {"FreePoints": 0, "GCDB": 1, "OzBargain": 2}
    enriched.sort(key=lambda x: (source_rank.get(x["source"], 9), x["title"].lower()))

    # ----- Plain text -----
    sections: list[str] = []
    sections.append(f"Daily Deal Stack Report — {today}")
    sections.append("Focus keywords: " + ", ".join(KEYWORDS))
    sections.append("")

    for src in ["FreePoints", "GCDB", "OzBargain"]:
        src_items = [x for x in enriched if x["source"] == src]
        if not src_items:
            continue
        sections.append(f"=== {src} (top {len(src_items)}) ===")
        for i, x in enumerate(src_items, 1):
            merch_txt = f" | Merchants: {', '.join(x['merchants'])}" if x.get("merchants") else ""
            hint_txt = f"\n    Stack hint: {x['hint']}" if x.get("hint") else ""
            sections.append(f"{i}. {x['title']}{merch_txt}\n    {x['link']}{hint_txt}")
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

    for src in ["FreePoints", "GCDB", "OzBargain"]:
        src_items = [x for x in enriched if x["source"] == src]
        rows = ""
        for i, x in enumerate(src_items, 1):
            meta = "Merchants: " + ", ".join(x["merchants"]) if x.get("merchants") else ""
            rows += row(i, x["title"], x["link"], meta=meta, hint=x.get("hint", ""))
        html_sections.append(card(src, f"Top {len(src_items)} items", deal_table(rows)))

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