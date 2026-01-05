#!/usr/bin/env python3
"""Test email output with stack recipes."""

import re

# Simplified helper functions
def extract_x(text):
    m = re.search(r"(\d{1,3})\s*x\b", (text or "").lower())
    return int(m.group(1)) if m else None

def detect_merchants(text):
    merchants = ["Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Woolworths", "Coles"]
    t = (text or "").lower()
    return [m for m in merchants if m.lower() in t]

def detect_cashback(text):
    t = (text or "").lower()
    found = []
    if "shopback" in t:
        found.append("ShopBack")
    return found

def detect_gift_card_type(text):
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
    title = item.get("title", "")
    gc_type = detect_gift_card_type(title)
    x = extract_x(title)
    merchants = item.get("merchants", [])
    
    steps = []
    
    if x:
        if x >= 20:
            steps.append(f"Activate {x}x points in your loyalty account before purchase.")
        else:
            steps.append(f"Ensure {x}x points promo is active in your account.")
    
    if gc_type == "ultimate":
        steps.append("Buy Ultimate gift cards at promoted merchant (front-load points return).")
        steps.append("Convert Ultimate cards online to JB Hi-Fi/Officeworks denominations (check 1-card-online.com.au limits).")
    elif gc_type == "apple":
        steps.append("Buy Apple gift cards at promoted merchant (front-load points return).")
        steps.append("Use Apple gift cards for Apple Store purchases (online or in-store, check online gift card limits).")
    elif gc_type == "generic":
        steps.append("Buy gift cards at promoted merchant (front-load points return).")
        if merchants:
            steps.append(f"Use gift cards at {merchants[0]} (check online gift card limits).")
    
    if item.get("cashback"):
        cashback_sites = ", ".join(item["cashback"][:2])
        steps.append(f"Optional: Use {cashback_sites} if portal allows gift-card/account-balance payments (check T&Cs).")
    
    return steps[:5]

# Mock deals
test_deals = [
    {
        "title": "Ultimate Gift Cards 20x Points at Woolworths",
        "link": "https://example.com/deal1",
        "score": 14
    },
    {
        "title": "Apple Gift Cards at Coles - 10x Points - ShopBack 3%",
        "link": "https://example.com/deal2",
        "score": 10
    }
]

# Build items
items = []
for deal in test_deals:
    item = {
        **deal,
        "merchants": detect_merchants(deal["title"]),
        "cashback": detect_cashback(deal["title"]),
        "hint": "Strong base return from points promo.",
        "why": "Gift cards front-load rewards and work across multiple merchants."
    }
    item["recipe"] = generate_stack_recipe(item)
    items.append(item)

# PLAIN TEXT OUTPUT
print("=" * 80)
print("📧 PLAIN TEXT EMAIL OUTPUT")
print("=" * 80)
print("\n🏆 Best Stacks Today — 2026-01-05\n")

for i, x in enumerate(items, 1):
    cb = f" | Cashback: {', '.join(x['cashback'])}" if x.get("cashback") else ""
    print(f"{i}. [{x['score']}] {x['title']}")
    print(f"   Merchants: {', '.join(x.get('merchants', []))}{cb}")
    print(f"   {x['link']}")
    if x.get("hint"):
        print(f"   Hint: {x['hint']}")
    if x.get("why"):
        print(f"   Why this stack works: {x['why']}")
    if x.get("recipe"):
        print(f"   📋 Stack Recipe:")
        for step_num, step in enumerate(x["recipe"], 1):
            print(f"      {step_num}. {step}")
    print()

# HTML OUTPUT (simplified visualization)
print("\n" + "=" * 80)
print("🌐 HTML EMAIL OUTPUT (Text Representation)")
print("=" * 80)
print("\n┌─────────────────────────────────────────────────────────────────┐")
print("│                  🏆 Best Stacks Today — 2026-01-05               │")
print("└─────────────────────────────────────────────────────────────────┘\n")

for i, x in enumerate(items, 1):
    print(f"{i}. [{x['score']}] {x['title']}")
    print(f"   Merchants: {', '.join(x['merchants'])}")
    if x.get('cashback'):
        print(f"   Cashback: {', '.join(x['cashback'])}")
    
    if x.get("hint"):
        print(f"\n   💡 Hint: {x['hint']}")
    
    if x.get("why"):
        print(f"\n   ✅ Why this stack works: {x['why']}")
    
    if x.get("recipe"):
        print(f"\n   ┌─ 📋 Stack Recipe ─────────────────────────────────────┐")
        for step_num, step in enumerate(x["recipe"], 1):
            print(f"   │  {step_num}. {step}")
        print(f"   └───────────────────────────────────────────────────────┘")
    
    print("\n" + "─" * 65 + "\n")

print("\n" + "=" * 80)
print("✅ Email format test complete!")
print("\nRecipe benefits:")
print("  • Actionable step-by-step instructions")
print("  • Visually distinct in email (blue box with ordered list)")
print("  • Includes all relevant cautions about limits and T&Cs")
print("  • Integrates seamlessly with existing 'hint' and 'why' sections")
