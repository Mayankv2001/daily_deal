#!/usr/bin/env python3
"""Comprehensive test of arbitrage integration in scoring and why_stack_works."""

import re

# Config
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

# Helper functions (simplified versions)
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

    return round(score, 1)

def why_stack_works(it):
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

    # Apple chip forward-compatibility
    chip_info = it.get("chip_info", {})
    if chip_info.get("chip") and chip_info.get("generation", 0) >= LATEST_KNOWN_GENERATION:
        reasons.append("Apple silicon generations are forward-compatible for price matching when model/SKU aligns.")
    
    # Physical retailer arbitrage opportunity
    arbitrage = it.get("arbitrage", {})
    if arbitrage.get("eligible") and arbitrage.get("confidence") in ["high", "medium"]:
        targets = arbitrage.get("targets", [])
        if targets:
            target_str = ", ".join(targets[:2])
            if arbitrage["confidence"] == "high":
                reasons.append(f"Physical stock signals suggest possible price match arbitrage at {target_str} (verify current policies).")
            else:
                reasons.append(f"Physical retailer deal may enable price comparison with {target_str} (check stock and policies).")

    return " ".join(reasons)

# Test deals
test_deals = [
    "MacBook Pro M4 at Officeworks $2399 - Click & Collect - 20x Points on Gift Cards",
    "Ultimate Gift Card 10x Points at Woolworths",
    "Apple M5 MacBook Air at JB Hi-Fi - In Stock - Price Beat Guarantee",
    "Samsung TV at The Good Guys - pickup available",
]

print("🧪 Full Pipeline Test: Arbitrage + Scoring + Explanations\n")
print("=" * 80)

results = []
for title in test_deals:
    item = {
        "title": title,
        "chip_info": detect_apple_chip(title),
    }
    item["arbitrage"] = calculate_arbitrage(item)
    item["score"] = score_item(item)
    item["why"] = why_stack_works(item)
    results.append(item)

# Sort by score (like the real script does)
results.sort(key=lambda x: x["score"], reverse=True)

for i, item in enumerate(results, 1):
    print(f"\n{i}. [{item['score']}] {item['title']}")
    print("-" * 80)
    
    arb = item["arbitrage"]
    print(f"   Arbitrage: {'✓ Eligible' if arb['eligible'] else '✗ Not eligible'}")
    if arb["eligible"]:
        print(f"   - Confidence: {arb['confidence'].upper()}")
        print(f"   - Targets: {', '.join(arb['targets'])}")
        
        # Show score breakdown
        conf_score = {"high": 4, "medium": 2, "low": 1, "none": 0}[arb["confidence"]]
        print(f"   - Score boost: +{conf_score}")
    
    print(f"\n   Why this stack works:")
    for reason in item["why"].split(". "):
        if reason.strip():
            print(f"     • {reason.strip()}.")

print("\n" + "=" * 80)
print("✅ Full pipeline test complete!")
print("\nKey takeaways:")
print("  • High confidence arbitrage: +4 score boost")
print("  • Medium confidence arbitrage: +2 score boost")
print("  • Conservative language: 'possible', 'may enable', 'verify policies'")
print("  • Top deals sorted by combined score (points + arbitrage + gift cards)")
