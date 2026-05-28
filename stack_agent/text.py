"""Text parsing and deal-signal detection helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse


MERCHANT_ALIASES: dict[str, list[str]] = {
    "JB Hi-Fi": ["jb hi-fi", "jb hifi", "jbhifi"],
    "Officeworks": ["officeworks", "office works"],
    "The Good Guys": ["the good guys", "good guys"],
    "Apple": ["apple store", "apple"],
    "Harvey Norman": ["harvey norman"],
    "Amazon": ["amazon", "amazon au", "amazon.com.au"],
    "Costco": ["costco"],
    "Coles": ["coles", "flybuys"],
    "Woolworths": ["woolworths", "woolies", "everyday rewards"],
    "Myer": ["myer"],
    "Big W": ["big w", "bigw"],
    "Target": ["target"],
    "Kmart": ["kmart"],
}

SUPERMARKETS = {"Coles", "Woolworths"}

PHYSICAL_RETAILERS: dict[str, list[str]] = {
    "Officeworks": ["JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "JB Hi-Fi": ["Officeworks", "The Good Guys", "Harvey Norman"],
    "The Good Guys": ["Officeworks", "JB Hi-Fi", "Harvey Norman"],
    "Apple": ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"],
    "Harvey Norman": ["Officeworks", "JB Hi-Fi", "The Good Guys"],
    "Costco": ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"],
}

STOCK_KEYWORDS = [
    "in stock",
    "click and collect",
    "c&c",
    "click & collect",
    "pick up",
    "pickup",
    "in-store",
    "in store",
    "store stock",
]

COUPON_KEYWORDS = ["coupon", "code", "promo code", "voucher"]

GIFT_CARD_ALIASES: dict[str, list[str]] = {
    "Apple Gift Card": ["apple gift card", "apple giftcard"],
    "Ultimate Gift Card": ["ultimate gift card", "ultimate giftcard", "ultimate"],
    "TCN Gift Card": ["tcn gift card", "tcn giftcard", "tcn"],
    "Super Swap": ["super swap", "superswap"],
    "Prezee": ["prezee"],
    "Amazon Gift Card": ["amazon gift card", "amazon giftcard"],
    "JB Hi-Fi Gift Card": ["jb hi-fi gift card", "jb hifi gift card", "jbhifi gift card"],
    "The Good Guys Gift Card": ["the good guys gift card"],
    "Officeworks Gift Card": ["officeworks gift card"],
}

GIFT_CARD_RETAILER_MAP: dict[str, list[str]] = {
    "Apple Gift Card": ["Apple"],
    "Ultimate Gift Card": ["JB Hi-Fi", "The Good Guys", "Officeworks", "Myer"],
    "TCN Gift Card": ["JB Hi-Fi", "The Good Guys", "Officeworks", "Myer", "Target"],
    "Super Swap": ["JB Hi-Fi", "The Good Guys", "Officeworks", "Amazon", "Myer"],
    "Prezee": ["JB Hi-Fi", "The Good Guys", "Officeworks", "Amazon", "Myer"],
    "Amazon Gift Card": ["Amazon"],
    "JB Hi-Fi Gift Card": ["JB Hi-Fi"],
    "The Good Guys Gift Card": ["The Good Guys"],
    "Officeworks Gift Card": ["Officeworks"],
}


def norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def lower_norm(value: str | None) -> str:
    return norm(value).lower()


def is_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_domain(value: str | None) -> str:
    if not is_http_url(value):
        return ""
    return urlparse(value or "").netloc.lower().replace("www.", "")


def query_tokens(query: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "deal", "deals", "sale", "buy"}
    return [t for t in re.findall(r"[a-z0-9]+", lower_norm(query)) if len(t) > 1 and t not in stop]


def text_matches_query(text: str, query: str) -> bool:
    tokens = query_tokens(query)
    if not tokens:
        return True
    haystack = lower_norm(text)
    return any(token in haystack for token in tokens)


def detect_merchants(text: str) -> list[str]:
    haystack = lower_norm(text)
    found = []
    for merchant, aliases in MERCHANT_ALIASES.items():
        if any(alias in haystack for alias in aliases):
            found.append(merchant)
    return found


def retailer_from_url(url: str) -> str | None:
    domain = extract_domain(url)
    if not domain:
        return None
    domain_aliases = {
        "jbhifi.com.au": "JB Hi-Fi",
        "officeworks.com.au": "Officeworks",
        "thegoodguys.com.au": "The Good Guys",
        "apple.com": "Apple",
        "harveynorman.com.au": "Harvey Norman",
        "amazon.com.au": "Amazon",
        "costco.com.au": "Costco",
        "coles.com.au": "Coles",
        "woolworths.com.au": "Woolworths",
        "myer.com.au": "Myer",
    }
    for needle, retailer in domain_aliases.items():
        if needle in domain:
            return retailer
    return None


def detect_gift_cards(text: str) -> list[str]:
    haystack = lower_norm(text)
    cards = []
    for card, aliases in GIFT_CARD_ALIASES.items():
        if any(alias in haystack for alias in aliases):
            cards.append(card)
    if not cards and ("gift card" in haystack or "giftcard" in haystack):
        cards.append("Generic Gift Card")
    return cards


def compatible_gift_cards(retailer: str | None) -> list[str]:
    if not retailer:
        return []
    cards = [
        card
        for card, retailers in GIFT_CARD_RETAILER_MAP.items()
        if retailer in retailers
    ]
    if retailer not in {"Coles", "Woolworths"}:
        merchant_card = f"{retailer} Gift Card"
        if merchant_card not in cards and retailer in MERCHANT_ALIASES:
            cards.append(merchant_card)
    return cards


def extract_price(text: str) -> float | None:
    matches = re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text or "")
    values = []
    for match in matches:
        try:
            values.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return min(values) if values else None


def extract_percent(text: str) -> float | None:
    matches = re.findall(r"(\d{1,2}(?:\.\d+)?)\s*%", text or "")
    values = []
    for match in matches:
        try:
            values.append(float(match))
        except ValueError:
            continue
    return max(values) if values else None


def extract_points_multiplier(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*x\b", lower_norm(text))
    return int(match.group(1)) if match else None


def points_multiplier_value(multiplier: int | None) -> float:
    if not multiplier:
        return 0.0
    return min(round(multiplier / 2.0, 2), 20.0)


def detect_cashback_portals(text: str) -> list[str]:
    haystack = lower_norm(text)
    found = []
    if "shopback" in haystack:
        found.append("ShopBack")
    if "topcashback" in haystack or "top cashback" in haystack:
        found.append("TopCashback")
    if "cashback" in haystack and not found:
        found.append("Cashback")
    return found


def has_stock_signal(text: str) -> bool:
    haystack = lower_norm(text)
    return any(keyword in haystack for keyword in STOCK_KEYWORDS)


def has_coupon_signal(text: str) -> bool:
    haystack = lower_norm(text)
    return any(keyword in haystack for keyword in COUPON_KEYWORDS)


def is_apple_product(text: str) -> bool:
    haystack = lower_norm(text)
    apple_terms = [
        "macbook",
        "ipad",
        "iphone",
        "airpods",
        "apple watch",
        "imac",
        "mac mini",
        "m1",
        "m2",
        "m3",
        "m4",
    ]
    return any(term in haystack for term in apple_terms)


def is_electronics_or_appliance(text: str) -> bool:
    haystack = lower_norm(text)
    terms = [
        "macbook",
        "ipad",
        "iphone",
        "tv",
        "laptop",
        "monitor",
        "fridge",
        "washer",
        "dryer",
        "dishwasher",
        "vacuum",
        "dyson",
        "console",
        "camera",
    ]
    return any(term in haystack for term in terms)


def dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
