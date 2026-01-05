#!/usr/bin/env python3
"""Test why_stack_works with Apple chip detection."""

import re

LATEST_KNOWN_GENERATION = 4  # M4 as of Jan 2026

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

def extract_x(text):
    m = re.search(r"(\d{1,3})\s*x\b", (text or "").lower())
    return int(m.group(1)) if m else None

def why_stack_works(it):
    """High-signal explanation of why this deal stacks TODAY."""
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
    
    # Apple chip forward-compatibility for price matching
    chip_info = it.get("chip_info", {})
    if chip_info.get("chip") and chip_info.get("generation", 0) >= LATEST_KNOWN_GENERATION:
        reasons.append("Apple silicon generations are forward-compatible for price matching when model/SKU aligns.")

    return " ".join(reasons)

# Test cases
test_items = [
    {
        "title": "MacBook Pro M4 Pro at JB Hi-Fi - 20x points",
        "merchants": ["JB Hi-Fi"],
        "chip_info": detect_apple_chip("MacBook Pro M4 Pro at JB Hi-Fi - 20x points")
    },
    {
        "title": "Apple M5 MacBook Air deal with gift card promo",
        "merchants": ["Apple"],
        "chip_info": detect_apple_chip("Apple M5 MacBook Air deal with gift card promo")
    },
    {
        "title": "M3 Max Mac Studio at Officeworks",
        "merchants": ["Officeworks"],
        "chip_info": detect_apple_chip("M3 Max Mac Studio at Officeworks")
    },
    {
        "title": "Ultimate Gift Cards 10x points at Woolworths",
        "merchants": ["Woolworths"],
        "chip_info": detect_apple_chip("Ultimate Gift Cards 10x points at Woolworths")
    }
]

print("🧪 Testing why_stack_works with Apple Chip Integration\n")
print("=" * 80)
print(f"Latest known generation: M{LATEST_KNOWN_GENERATION}\n")

for i, item in enumerate(test_items, 1):
    print(f"{i}. {item['title']}")
    print("-" * 80)
    
    chip_info = item.get("chip_info", {})
    if chip_info.get("chip"):
        print(f"   Chip detected: {chip_info['chip']} (Gen: M{chip_info.get('generation')}, Tier: {chip_info.get('tier')})")
        if chip_info.get('generation', 0) >= LATEST_KNOWN_GENERATION:
            print(f"   ✅ Generation >= M{LATEST_KNOWN_GENERATION} (latest known)")
        else:
            print(f"   ⚠️  Generation < M{LATEST_KNOWN_GENERATION} (older)")
    else:
        print("   No chip detected")
    
    why = why_stack_works(item)
    print(f"\n   Why this stack works:")
    for reason in why.split(". "):
        if reason.strip():
            print(f"     • {reason.strip()}.")
    print()

print("=" * 80)
print("✅ Test complete!")
