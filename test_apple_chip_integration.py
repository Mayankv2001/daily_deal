#!/usr/bin/env python3
"""Quick test to verify Apple chip detection integration."""

import sys
import re

# Copy relevant functions for testing
def detect_apple_chip(text: str) -> dict:
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

PHYSICAL_RETAILERS = [
    "Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "Harvey Norman", "Bing Lee"
]

STOCK_KEYWORDS = [
    "in stock", "click and collect", "c&c", "pick up", "in-store", "in store", "pickup"
]

def detect_physical_retailer(text: str) -> list[str]:
    t = (text or "").lower()
    found = []
    for r in PHYSICAL_RETAILERS:
        if r.lower() in t:
            found.append(r)
    return found

def has_stock_signal(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in STOCK_KEYWORDS)

def calculate_confidence(item: dict) -> str:
    chip_info = item.get("chip_info", {})
    physical = item.get("physical_retailers", [])
    has_stock = item.get("has_stock_signal", False)
    
    if chip_info.get("chip"):
        if physical and has_stock:
            return "HIGH"
        if not physical or not has_stock:
            return "LOW"
    
    if item.get("merchants"):
        return "MEDIUM"
    
    return "LOW"

# Test cases
test_deals = [
    "MacBook Pro M5 Pro at Officeworks - In Stock Click & Collect",
    "Apple M4 MacBook Air on sale at JB Hi-Fi - pickup available",
    "M6 Ultra Mac Studio deal - online only",
    "m3 max MacBook - Amazon exclusive",
    "Gift card deal: 20x points on Ultimate cards at Woolworths",
]

print("🧪 Apple Chip Integration Test\n")
print("=" * 80)

for i, title in enumerate(test_deals, 1):
    print(f"\n{i}. {title}")
    print("-" * 80)
    
    chip_info = detect_apple_chip(title)
    physical = detect_physical_retailer(title)
    has_stock = has_stock_signal(title)
    
    item = {
        "title": title,
        "chip_info": chip_info,
        "physical_retailers": physical,
        "has_stock_signal": has_stock,
        "merchants": physical,  # simplified
    }
    
    confidence = calculate_confidence(item)
    
    print(f"   Chip: {chip_info.get('chip') or 'None'}")
    if chip_info.get('chip'):
        print(f"   Generation: M{chip_info.get('generation')}")
        print(f"   Tier: {chip_info.get('tier')}")
    print(f"   Physical Retailers: {', '.join(physical) if physical else 'None'}")
    print(f"   Stock Signal: {'✓ Yes' if has_stock else '✗ No'}")
    print(f"   Confidence: {confidence}")
    print(f"   Is Apple: {chip_info.get('chip') is not None}")
    
    # Show what would happen
    if chip_info.get('chip'):
        if confidence == "HIGH":
            print(f"   → ✅ INCLUDED in main list with price match suggestion")
        elif confidence == "LOW":
            print(f"   → ⚠️  EXCLUDED from main list (shown in low confidence section)")

print("\n" + "=" * 80)
print("✅ Test complete!")
