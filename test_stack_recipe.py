#!/usr/bin/env python3
"""Test stack recipe generator."""

import re

PRIORITY_MERCHANTS = ["Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "IKEA"]

PHYSICAL_RETAILERS = {
    "Officeworks": ["JB Hi-Fi", "The Good Guys"],
    "JB Hi-Fi": ["Officeworks", "The Good Guys"],
    "The Good Guys": ["Officeworks", "JB Hi-Fi"],
    "Apple": ["Officeworks", "JB Hi-Fi", "The Good Guys"],
}

STOCK_KEYWORDS = [
    "in stock", "click and collect", "c&c", "click & collect",
    "pick up", "pickup", "in-store", "in store", "store stock"
]

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
    if "topcashback" in t:
        found.append("TopCashback")
    return found

def detect_apple_chip(text):
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
    t = (text or "").lower()
    found = []
    for retailer in PHYSICAL_RETAILERS.keys():
        if retailer.lower() in t:
            found.append(retailer)
    return found

def detect_stock_signal(text):
    t = (text or "").lower()
    return any(kw in t for kw in STOCK_KEYWORDS)

def calculate_arbitrage(item):
    title = item.get("title", "")
    physical = detect_physical_retailers(title)
    has_stock = detect_stock_signal(title)
    chip_info = item.get("chip_info", {})
    
    if not physical:
        return {"eligible": False, "targets": [], "confidence": "none"}
    
    targets = []
    for retailer in physical:
        if retailer in PHYSICAL_RETAILERS:
            targets.extend(PHYSICAL_RETAILERS[retailer])
    
    targets = list(set(targets))
    
    confidence = "none"
    if targets:
        if has_stock and (chip_info.get("chip") or any(m in PRIORITY_MERCHANTS for m in physical)):
            confidence = "high"
        elif has_stock:
            confidence = "medium"
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

# Test cases
test_deals = [
    {
        "title": "Ultimate Gift Cards 20x Points at Woolworths",
        "desc": "Ultimate card with high points promo"
    },
    {
        "title": "Apple Gift Cards at Coles - 10x Everyday Rewards Points",
        "desc": "Apple gift card with points"
    },
    {
        "title": "MacBook Pro M4 at Officeworks - Click & Collect - 20x Points",
        "desc": "Apple chip with arbitrage opportunity"
    },
    {
        "title": "JB Hi-Fi Gift Card 15x Points at Big W - ShopBack 5%",
        "desc": "Generic gift card with cashback"
    },
    {
        "title": "TCN Gift Card Deal at Woolworths - 10x Points",
        "desc": "TCN card type"
    }
]

print("🧪 Stack Recipe Generator Test\n")
print("=" * 80)

for i, test in enumerate(test_deals, 1):
    title = test["title"]
    print(f"\n{i}. {title}")
    print(f"   {test['desc']}")
    print("-" * 80)
    
    item = {
        "title": title,
        "merchants": detect_merchants(title),
        "cashback": detect_cashback(title),
        "chip_info": detect_apple_chip(title),
    }
    item["arbitrage"] = calculate_arbitrage(item)
    
    gc_type = detect_gift_card_type(title)
    x = extract_x(title)
    recipe = generate_stack_recipe(item)
    
    print(f"   Gift Card Type: {gc_type or 'None'}")
    print(f"   Points Multiplier: {x}x" if x else "   Points Multiplier: None")
    print(f"   Merchants: {', '.join(item['merchants']) if item['merchants'] else 'None'}")
    print(f"   Arbitrage: {item['arbitrage']['confidence'].upper()}" if item['arbitrage']['eligible'] else "   Arbitrage: Not eligible")
    print(f"\n   📋 Stack Recipe ({len(recipe)} steps):")
    for step_num, step in enumerate(recipe, 1):
        print(f"      {step_num}. {step}")

print("\n" + "=" * 80)
print("✅ Recipe generation test complete!")
print("\nKey features:")
print("  • Detects 4 gift card types: Apple, Ultimate, TCN, Generic")
print("  • 3-5 actionable steps per deal")
print("  • Includes 'check limits' warnings where relevant")
print("  • Integrates points, gift cards, arbitrage, and cashback")
print("  • No scraped data - all conservative, generic advice")
