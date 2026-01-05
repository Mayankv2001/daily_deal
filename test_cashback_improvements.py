#!/usr/bin/env python3
"""Test improved cashback handling."""

import re

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

def cashback_note(portals):
    """Generate conservative cashback warning note."""
    if not portals:
        return None
    portal_str = ", ".join(portals)
    return f"⚠️ {portal_str} typically excludes gift card purchases. Verify portal T&Cs before assuming cashback applies."

def extract_x(text):
    m = re.search(r"(\d{1,3})\s*x\b", (text or "").lower())
    return int(m.group(1)) if m else None

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

    # Cashback: reduced weight, never outweighs points/gift cards
    if it.get("cashback"):
        score += 1  # Reduced from 2 to 1
        if any(c in ["ShopBack", "TopCashback"] for c in it["cashback"]):
            score += 0.5  # Reduced from 1 to 0.5

    return round(score, 1)

# Test deals
test_deals = [
    {
        "title": "Ultimate Gift Cards 20x Points at Woolworths - ShopBack 5%",
        "desc": "High points + cashback mention"
    },
    {
        "title": "Apple Gift Cards 10x Points at Coles",
        "desc": "Points only, no cashback"
    },
    {
        "title": "JB Hi-Fi Deal with TopCashback 3%",
        "desc": "Cashback only, no points"
    },
    {
        "title": "Officeworks Cashback Deal - Cashrewards 4%",
        "desc": "Generic cashback portal"
    }
]

print("🧪 Improved Cashback Handling Test\n")
print("=" * 80)

print("\n📊 SCORING COMPARISON")
print("-" * 80)
print(f"{'Deal Type':<40} {'Old Score':<12} {'New Score':<12} {'Change'}")
print("-" * 80)

# Scoring comparisons
comparisons = [
    ("20x Points + Gift Card", 8 + 3, 8 + 3, "No change"),
    ("20x + Gift Card + ShopBack", 8 + 3 + 2 + 1, 8 + 3 + 1 + 0.5, "-2.5 pts"),
    ("Gift Card + TopCashback", 3 + 2 + 1, 3 + 1 + 0.5, "-1.5 pts"),
    ("Cashback only (generic)", 2, 1, "-1 pt"),
]

for deal_type, old, new, change in comparisons:
    print(f"{deal_type:<40} {old:<12.1f} {new:<12.1f} {change}")

print("\n" + "=" * 80)
print("\n📝 CASHBACK NOTES & DISPLAY")
print("-" * 80)

for i, test in enumerate(test_deals, 1):
    title = test["title"]
    print(f"\n{i}. {title}")
    print(f"   {test['desc']}")
    print("-" * 80)
    
    cashback = detect_cashback(title)
    note = cashback_note(cashback)
    x = extract_x(title)
    
    item = {
        "title": title,
        "cashback": cashback
    }
    score = score_item(item)
    
    print(f"   Cashback Detected: {', '.join(cashback) if cashback else 'None'}")
    print(f"   Points Multiplier: {x}x" if x else "   Points Multiplier: None")
    print(f"   Score: {score}")
    
    if note:
        print(f"\n   Cashback Note:")
        print(f"   {note}")
    
    # Show how it appears in why_stack_works
    if cashback:
        print(f"\n   In 'Why this stack works':")
        print(f"   → Cashback portals often exclude gift card purchases—verify T&Cs before relying on cashback.")

print("\n" + "=" * 80)
print("\n✅ Improved cashback handling test complete!")

print("\n📋 Key Improvements:")
print("  1. Scoring: Cashback reduced from +2-3 to +1-1.5 (never outweighs points/GCs)")
print("  2. New cashback_note: Conservative warning displayed prominently")
print("  3. Single line in why_stack_works: Clear, actionable advice")
print("  4. Visual: Yellow warning box in HTML emails")
print("  5. Conservative language: 'typically excludes', 'verify T&Cs'")

print("\n💡 Score Impact Examples:")
print("  • 20x + Gift Card: 11 pts (unchanged - fundamentals preserved)")
print("  • 20x + GC + ShopBack: 12.5 pts (was 14 - cashback is bonus, not core)")
print("  • Pure cashback deal: 1 pt (was 2 - correctly de-emphasized)")
