#!/usr/bin/env python3
"""Test physical retailer arbitrage detection."""

import re

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

PRIORITY_MERCHANTS = ["Officeworks", "JB Hi-Fi", "The Good Guys", "Apple", "IKEA"]
LATEST_KNOWN_GENERATION = 4

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

def score_arbitrage(arbitrage):
    """Calculate score boost from arbitrage."""
    if not arbitrage.get("eligible"):
        return 0
    
    confidence = arbitrage.get("confidence", "none")
    if confidence == "high":
        return 4
    elif confidence == "medium":
        return 2
    elif confidence == "low":
        return 1
    return 0

# Test cases
test_deals = [
    {
        "title": "MacBook Pro M4 at Officeworks - Click and Collect Available",
        "desc": "High confidence: Apple chip + physical retailer + stock signal"
    },
    {
        "title": "Apple M5 MacBook Air $1699 at JB Hi-Fi - In Stock",
        "desc": "High confidence: Apple chip + physical + stock"
    },
    {
        "title": "The Good Guys sale on Samsung TVs - pickup available",
        "desc": "Medium confidence: physical + stock, no Apple chip"
    },
    {
        "title": "Officeworks deal on office supplies",
        "desc": "Low confidence: physical retailer but no stock signal"
    },
    {
        "title": "Amazon exclusive deal on laptops",
        "desc": "Not eligible: no physical retailer"
    },
    {
        "title": "Gift card deal 20x points at Woolworths - in store",
        "desc": "Not eligible: not a price-matchable physical retailer"
    }
]

print("🧪 Physical Retailer Arbitrage Detection Test\n")
print("=" * 80)

for i, test in enumerate(test_deals, 1):
    title = test["title"]
    print(f"\n{i}. {title}")
    print(f"   Description: {test['desc']}")
    print("-" * 80)
    
    physical = detect_physical_retailers(title)
    has_stock = detect_stock_signal(title)
    chip_info = detect_apple_chip(title)
    
    item = {
        "title": title,
        "chip_info": chip_info
    }
    
    arbitrage = calculate_arbitrage(item)
    score_boost = score_arbitrage(arbitrage)
    
    print(f"   Physical Retailers: {', '.join(physical) if physical else 'None'}")
    print(f"   Stock Signal: {'✓ Yes' if has_stock else '✗ No'}")
    print(f"   Apple Chip: {chip_info.get('chip') or 'None'}")
    print(f"   ")
    print(f"   Arbitrage Eligible: {'✓ Yes' if arbitrage['eligible'] else '✗ No'}")
    print(f"   Arbitrage Targets: {', '.join(arbitrage['targets']) if arbitrage['targets'] else 'None'}")
    print(f"   Confidence: {arbitrage['confidence'].upper()}")
    print(f"   Score Boost: +{score_boost}")
    
    # Show what would be added to why_stack_works
    if arbitrage.get("eligible") and arbitrage.get("confidence") in ["high", "medium"]:
        targets = arbitrage.get("targets", [])
        if targets:
            target_str = ", ".join(targets[:2])
            if arbitrage["confidence"] == "high":
                hint = f"Physical stock signals suggest possible price match arbitrage at {target_str} (verify current policies)."
            else:
                hint = f"Physical retailer deal may enable price comparison with {target_str} (check stock and policies)."
            print(f"   → Hint: {hint}")

print("\n" + "=" * 80)
print("✅ Test complete!")
