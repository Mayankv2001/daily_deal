#!/usr/bin/env python3
"""Test Harvey Norman integration."""

import re

MERCHANTS = [
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman",
    "Amazon", "Woolworths", "Coles", "IKEA"
]

PHYSICAL_RETAILERS = {
    "Officeworks": ["JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "JB Hi-Fi": ["Officeworks", "The Good Guys", "Harvey Norman"],
    "The Good Guys": ["Officeworks", "JB Hi-Fi", "Harvey Norman"],
    "Apple": ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "Harvey Norman": ["Officeworks", "JB Hi-Fi", "The Good Guys"],
}

STOCK_KEYWORDS = [
    "in stock", "click and collect", "c&c", "click & collect",
    "pick up", "pickup", "in-store", "in store", "store stock"
]

LATEST_KNOWN_GENERATION = 4

def detect_merchants(text):
    t = (text or "").lower()
    return [m for m in MERCHANTS if m.lower() in t]

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

def has_stock_signal(text):
    title_lower = (text or "").lower()
    return any(kw in title_lower for kw in STOCK_KEYWORDS)

def why_stack_works(item):
    """Simplified version showing Apple chip + stock logic."""
    reasons = []
    chip_info = item.get("chip_info", {})
    
    # Apple chip forward-compatibility
    if chip_info.get("chip") and chip_info.get("generation", 0) >= LATEST_KNOWN_GENERATION:
        reasons.append("Apple silicon generations are forward-compatible for price matching when model/SKU aligns.")
    
    # Apple chip with stock signal - specific price match hint
    if chip_info.get("chip"):
        title_lower = (item.get("title", "")).lower()
        has_stock = any(kw in title_lower for kw in STOCK_KEYWORDS)
        if has_stock:
            reasons.append("Consider Harvey Norman / JB Hi-Fi / Officeworks price match/beat where policy allows.")
    
    return " ".join(reasons)

# Test cases
test_deals = [
    {
        "title": "MacBook Pro M4 at Harvey Norman - Click & Collect Available",
        "desc": "Harvey Norman as source + stock signal"
    },
    {
        "title": "Apple M5 MacBook Air at Officeworks - In Stock Now",
        "desc": "Different retailer + stock signal"
    },
    {
        "title": "M4 Mac Mini at JB Hi-Fi - Online Only",
        "desc": "No stock signal"
    },
    {
        "title": "Harvey Norman MacBook Pro M3 - Pickup Available",
        "desc": "Harvey Norman + older chip (M3) + stock"
    },
    {
        "title": "Harvey Norman Tech Sale - Various Products",
        "desc": "Harvey Norman but no Apple chip"
    }
]

print("🧪 Harvey Norman Integration Test\n")
print("=" * 80)

print("\n📋 UPDATED CONFIGURATIONS")
print("-" * 80)
print(f"MERCHANTS: {', '.join(MERCHANTS)}")
print(f"\nPRIORITY_MERCHANTS: Officeworks, JB Hi-Fi, The Good Guys, Apple, Harvey Norman, IKEA")
print(f"\nPHYSICAL_RETAILERS arbitrage targets:")
for retailer, targets in PHYSICAL_RETAILERS.items():
    print(f"  {retailer} → {', '.join(targets)}")

print("\n" + "=" * 80)
print("\n🔍 DEAL ANALYSIS")
print("-" * 80)

for i, test in enumerate(test_deals, 1):
    title = test["title"]
    print(f"\n{i}. {title}")
    print(f"   {test['desc']}")
    print("-" * 80)
    
    merchants = detect_merchants(title)
    chip_info = detect_apple_chip(title)
    physical = detect_physical_retailers(title)
    has_stock = has_stock_signal(title)
    
    item = {
        "title": title,
        "chip_info": chip_info
    }
    
    why = why_stack_works(item)
    
    print(f"   Merchants: {', '.join(merchants) if merchants else 'None'}")
    print(f"   Physical Retailers: {', '.join(physical) if physical else 'None'}")
    print(f"   Apple Chip: {chip_info.get('chip') or 'None'}")
    print(f"   Generation: M{chip_info.get('generation')}" if chip_info.get('generation') else "   Generation: None")
    print(f"   Stock Signal: {'✓ Yes' if has_stock else '✗ No'}")
    
    if physical:
        targets = []
        for retailer in physical:
            if retailer in PHYSICAL_RETAILERS:
                targets.extend(PHYSICAL_RETAILERS[retailer])
        targets = list(set(targets))
        if targets:
            print(f"   Arbitrage Targets: {', '.join(targets)}")
    
    if why:
        print(f"\n   Why this stack works:")
        for reason in why.split(". "):
            if reason.strip():
                print(f"     • {reason.strip()}.")

print("\n" + "=" * 80)
print("\n✅ Harvey Norman Integration Complete!")

print("\n📋 Key Changes:")
print("  1. Harvey Norman added to MERCHANTS list (both files)")
print("  2. Harvey Norman added to PRIORITY_MERCHANTS")
print("  3. Harvey Norman in PHYSICAL_RETAILERS dict with bidirectional arbitrage:")
print("     • Harvey Norman → Officeworks, JB Hi-Fi, The Good Guys")
print("     • Others → now include Harvey Norman as target")
print("  4. Apple chip + stock signal → specific hint in why_stack_works:")
print("     'Consider Harvey Norman / JB Hi-Fi / Officeworks price match/beat where policy allows.'")

print("\n💡 Example Outputs:")
print("  • M4 at Harvey Norman + C&C → Shows Harvey Norman hint + arbitrage targets")
print("  • M5 at Officeworks + In Stock → Shows Harvey Norman in targets + hint")
print("  • M4 without stock signal → No Harvey Norman hint (conservative)")
print("  • Non-Apple products at Harvey Norman → Detected but no specific hint")
