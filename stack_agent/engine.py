"""Stack planning engine for product-search deal recommendations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import SourceItem, StackRecommendation, StackSearchResult
from .sources import collect_live_sources
from .text import (
    GIFT_CARD_ALIASES,
    PHYSICAL_RETAILERS,
    compatible_gift_cards,
    dedupe_strings,
    detect_cashback_portals,
    detect_gift_cards,
    detect_merchants,
    extract_percent,
    extract_points_multiplier,
    extract_price,
    has_coupon_signal,
    has_stock_signal,
    is_electronics_or_appliance,
    is_http_url,
    is_apple_product,
    norm,
    points_multiplier_value,
    retailer_from_url,
    text_matches_query,
)


SourceCollector = Callable[[str, str | None, int], tuple[list[SourceItem], list[str]]]


class StackAgent:
    """Build aggressive deal-stack recommendations from live source items."""

    def __init__(self, source_collector: SourceCollector | None = None):
        self.source_collector = source_collector or collect_live_sources

    def search(self, query: str, url: str | None = None, max_results: int = 5) -> StackSearchResult:
        query = norm(query)
        if not query and url:
            query = url
        if not query:
            raise ValueError("query is required")
        if url and not is_http_url(url):
            raise ValueError("url must be an http or https URL")

        max_results = min(max(int(max_results or 5), 1), 10)
        items, errors = self.source_collector(query, url, max(max_results * 2, 6))
        recommendations = self._build_recommendations(query, url, items)
        if not recommendations:
            recommendations = [self._fallback_recommendation(query, url, items)]

        recommendations.sort(
            key=lambda rec: (
                rec.score,
                _confidence_rank(rec.estimated_saving.get("confidence")),
                len(rec.sources),
            ),
            reverse=True,
        )
        return StackSearchResult(
            query=query,
            recommendations=recommendations[:max_results],
            source_errors=errors,
        )

    def _build_recommendations(
        self,
        query: str,
        url: str | None,
        items: list[SourceItem],
    ) -> list[StackRecommendation]:
        base_deals = self._base_deals(query, url, items)
        offers = [item for item in items if item not in base_deals]
        recommendations = []
        for base in base_deals[:8]:
            recommendations.append(self._recommend_for_base(query, base, offers))
        return recommendations

    def _base_deals(self, query: str, url: str | None, items: list[SourceItem]) -> list[SourceItem]:
        base = [
            item
            for item in items
            if item.kind == "base_deal" or item.source == "OzBargain" or item.metadata.get("input_url")
        ]
        ranked = []
        for item in base:
            text = f"{item.title} {item.text}"
            score = 0
            if item.metadata.get("input_url"):
                score += 5
            if text_matches_query(text, query):
                score += 3
            if item.price:
                score += 2
            if item.retailer:
                score += 1
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        out = [item for score, item in ranked if score > 0]
        if out:
            return out

        retailer = retailer_from_url(url or "") or _first(detect_merchants(query))
        return [
            SourceItem(
                source="User query",
                title=query,
                url=url or "",
                kind="base_deal",
                retailer=retailer,
                price=None,
                text=query,
                metadata={"synthetic": True},
            )
        ]

    def _recommend_for_base(
        self,
        query: str,
        base: SourceItem,
        offers: list[SourceItem],
    ) -> StackRecommendation:
        combined_text = norm(f"{query} {base.title} {base.text} {base.url}")
        retailer = base.retailer or retailer_from_url(base.url) or _first(detect_merchants(combined_text)) or "Unknown retailer"
        price = base.price or extract_price(combined_text)
        cards = compatible_gift_cards(retailer)
        explicit_cards = detect_gift_cards(combined_text)
        cards = dedupe_strings(explicit_cards + cards)

        gift_offers = [offer for offer in offers if _gift_offer_matches(offer, cards, retailer, query)]
        cashback_offers = [offer for offer in offers if _cashback_offer_matches(offer, retailer, query)]
        source_supported_coupon = _has_source_supported_coupon(base, offers)
        price_match_targets = _price_match_targets(retailer, combined_text)

        gift_percent = _best_gift_card_percent(gift_offers + [base])
        cashback_percent = _best_cashback_percent(cashback_offers)
        product_discount_percent = _product_discount_percent(combined_text)
        price_match_percent = 2.0 if price_match_targets and has_stock_signal(combined_text) else 1.0 if price_match_targets else 0.0

        estimated_percent = min(
            round(gift_percent + cashback_percent + product_discount_percent + price_match_percent, 2),
            45.0,
        )
        amount = round(price * estimated_percent / 100, 2) if price and estimated_percent else None

        risk_level = _risk_level(
            cards=cards,
            gift_percent=gift_percent,
            cashback_percent=cashback_percent,
            coupon=has_coupon_signal(combined_text),
            source_supported_coupon=source_supported_coupon,
            retailer=retailer,
        )
        confidence = _confidence(
            price=price,
            gift_percent=gift_percent,
            cashback_percent=cashback_percent,
            product_discount_percent=product_discount_percent,
            gift_offers=gift_offers,
            cashback_offers=cashback_offers,
            cards=cards,
            risk_level=risk_level,
        )

        steps = _stack_steps(
            query=query,
            base=base,
            retailer=retailer,
            cards=cards,
            gift_offers=gift_offers,
            cashback_offers=cashback_offers,
            price_match_targets=price_match_targets,
            source_supported_coupon=source_supported_coupon,
        )
        warnings = _warnings(
            retailer=retailer,
            cards=cards,
            cashback_percent=cashback_percent,
            coupon=has_coupon_signal(combined_text),
            source_supported_coupon=source_supported_coupon,
            price_match_targets=price_match_targets,
            apple_route=is_apple_product(combined_text) or retailer == "Apple",
            no_stack=estimated_percent == 0,
        )
        sources = dedupe_strings([base.source] + [offer.source for offer in gift_offers + cashback_offers])
        evidence = _evidence([base] + gift_offers[:3] + cashback_offers[:2])
        score = _score(estimated_percent, confidence, risk_level, sources, price)
        title = _title_for_route(retailer, cards, gift_percent, cashback_percent, price_match_targets, estimated_percent)

        return StackRecommendation(
            title=title,
            retailer=retailer,
            base_deal={
                "price": price,
                "source": base.source,
                "url": base.url,
                "title": base.title,
            },
            stack_steps=steps,
            estimated_saving={
                "percent": estimated_percent,
                "amount": amount,
                "confidence": confidence,
            },
            risk_level=risk_level,
            warnings=warnings,
            sources=sources or [base.source],
            score=score,
            evidence=evidence,
        )

    def _fallback_recommendation(
        self,
        query: str,
        url: str | None,
        items: list[SourceItem],
    ) -> StackRecommendation:
        sources = dedupe_strings([item.source for item in items]) or ["No live source match"]
        return StackRecommendation(
            title="No clear stack found yet",
            retailer=_first(detect_merchants(query)) or "Unknown retailer",
            base_deal={"price": None, "source": "User query", "url": url or "", "title": query},
            stack_steps=[
                "Use the cheapest verified product deal first.",
                "Check GCDB multi-retailer and merchant pages for gift card compatibility before buying cards.",
                "Check FreePoints for current Coles or Woolworths gift card points promos.",
                "Only add cashback after checking portal terms for gift card, coupon, and category exclusions.",
            ],
            estimated_saving={"percent": 0.0, "amount": None, "confidence": "low"},
            risk_level="medium",
            warnings=[
                "No reliable live stack was detected for this query.",
                "Verify gift card acceptance and cashback terms before purchase.",
            ],
            sources=sources,
            score=0.0,
            evidence=_evidence(items[:5]),
        )


def _gift_offer_matches(offer: SourceItem, cards: list[str], retailer: str, query: str) -> bool:
    text = f"{offer.title} {offer.text}"
    lower = text.lower()
    if offer.kind not in {"gift_card_offer", "points_offer"} and not detect_gift_cards(text):
        return False
    if text_matches_query(text, query):
        return True
    if retailer != "Unknown retailer" and retailer.lower() in lower:
        return True
    for card in cards:
        aliases = GIFT_CARD_ALIASES.get(card, [card.lower()])
        if any(alias in lower for alias in aliases):
            return True
    return any(term in lower for term in ["ultimate", "tcn", "prezee", "super swap", "apple gift", "gift card"])


def _cashback_offer_matches(offer: SourceItem, retailer: str, query: str) -> bool:
    text = f"{offer.title} {offer.text}"
    if offer.kind == "cashback_offer" or detect_cashback_portals(text):
        if retailer != "Unknown retailer" and retailer.lower() in text.lower():
            return True
        return text_matches_query(text, query) or bool(offer.metadata.get("portals"))
    return False


def _best_gift_card_percent(items: list[SourceItem]) -> float:
    values = []
    for item in items:
        text = f"{item.title} {item.text}"
        multiplier = extract_points_multiplier(text)
        if multiplier:
            values.append(points_multiplier_value(multiplier))
        percent = item.metadata.get("percent") or extract_percent(text)
        if percent and any(term in text.lower() for term in ["gift", "card", "points", "flybuys", "everyday rewards"]):
            values.append(min(float(percent), 25.0))
    return round(max(values) if values else 0.0, 2)


def _best_cashback_percent(items: list[SourceItem]) -> float:
    values = []
    for item in items:
        percent = item.metadata.get("percent") or extract_percent(f"{item.title} {item.text}")
        if percent:
            values.append(min(float(percent), 20.0))
        elif item.kind == "cashback_offer":
            values.append(2.0)
    return round(max(values) if values else 0.0, 2)


def _product_discount_percent(text: str) -> float:
    lower = text.lower()
    percent = extract_percent(text)
    if percent and any(term in lower for term in ["off", "save", "discount"]):
        return min(float(percent), 30.0)
    return 0.0


def _has_source_supported_coupon(base: SourceItem, offers: list[SourceItem]) -> bool:
    text = f"{base.title} {base.text}"
    if not has_coupon_signal(text):
        return False
    lower = text.lower()
    if "ozbargain" in base.source.lower() and any(term in lower for term in ["coupon", "code", "promo"]):
        return True
    return any("coupon" in f"{offer.title} {offer.text}".lower() for offer in offers)


def _price_match_targets(retailer: str, text: str) -> list[str]:
    if retailer in PHYSICAL_RETAILERS:
        if is_electronics_or_appliance(text) or has_stock_signal(text) or is_apple_product(text):
            return PHYSICAL_RETAILERS[retailer]
    if is_apple_product(text):
        return ["Officeworks", "JB Hi-Fi", "The Good Guys", "Harvey Norman"]
    return []


def _risk_level(
    cards: list[str],
    gift_percent: float,
    cashback_percent: float,
    coupon: bool,
    source_supported_coupon: bool,
    retailer: str,
) -> str:
    if cashback_percent and (cards or gift_percent):
        return "high"
    if cashback_percent and coupon and not source_supported_coupon:
        return "high"
    if retailer == "Unknown retailer" and (cards or cashback_percent):
        return "high"
    if cards or gift_percent or cashback_percent:
        return "medium"
    return "low"


def _confidence(
    price: float | None,
    gift_percent: float,
    cashback_percent: float,
    product_discount_percent: float,
    gift_offers: list[SourceItem],
    cashback_offers: list[SourceItem],
    cards: list[str],
    risk_level: str,
) -> str:
    live_value = bool(gift_offers or cashback_offers)
    if price and live_value and (gift_percent or cashback_percent or product_discount_percent) and risk_level != "high":
        return "high"
    if live_value or cards or price:
        return "medium" if risk_level != "high" else "low"
    return "low"


def _stack_steps(
    query: str,
    base: SourceItem,
    retailer: str,
    cards: list[str],
    gift_offers: list[SourceItem],
    cashback_offers: list[SourceItem],
    price_match_targets: list[str],
    source_supported_coupon: bool,
) -> list[str]:
    steps = []
    if base.url:
        steps.append(f"Start from the live {base.source} result for {query}: {base.title}.")
    else:
        steps.append(f"Start by finding the cheapest verified retailer price for {query}.")

    if gift_offers and cards:
        offer = gift_offers[0]
        card_text = ", ".join(cards[:3])
        steps.append(f"Buy eligible {card_text} through the live {offer.source} offer: {offer.title}.")
        steps.append(f"Use the gift card at {retailer}; check split-payment, online limit, and excluded-category rules first.")
    elif cards:
        card_text = ", ".join(cards[:3])
        steps.append(f"Check GCDB for {card_text} compatibility, then buy only if a current points or discount promo is live.")
        steps.append(f"Use the compatible gift card at {retailer} after confirming the exact merchant/category is included.")

    if cashback_offers:
        offer = cashback_offers[0]
        steps.append(f"Optionally click through {offer.source} for cashback on {retailer}; treat this as risky if paying with gift cards.")

    if price_match_targets:
        steps.append(f"Compare the deal against {', '.join(price_match_targets[:3])} for price match or price beat opportunities.")

    if source_supported_coupon:
        steps.append("Use the source-listed coupon/code only if the cashback portal terms also allow it.")

    if len(steps) == 1:
        steps.append("No reliable gift card or cashback stack was detected; use the cheapest base deal and monitor GCDB/FreePoints.")

    steps.append("Before purchase, verify gift card acceptance, cashback exclusions, expiry dates, and current stock.")
    return steps[:7]


def _warnings(
    retailer: str,
    cards: list[str],
    cashback_percent: float,
    coupon: bool,
    source_supported_coupon: bool,
    price_match_targets: list[str],
    apple_route: bool,
    no_stack: bool,
) -> list[str]:
    warnings = ["Verify gift card acceptance and cashback terms before purchase."]
    if cards:
        warnings.append("Multi-retailer gift card support can change; check the issuer and GCDB before buying cards.")
    if cashback_percent:
        warnings.append("Cashback may be rejected when paying with gift cards, store credit, or unsupported coupon codes.")
    if coupon and not source_supported_coupon:
        warnings.append("Coupon plus cashback is high risk unless the portal explicitly lists that code.")
    if price_match_targets:
        warnings.append("Price match and price beat policies depend on exact SKU, stock, delivery, and retailer policy.")
    if apple_route or retailer == "Apple":
        warnings.append("Apple gift card redemption and online order limits can affect large purchases.")
    if no_stack:
        warnings.append("No-stack result: the best path may be the cheapest base deal only.")
    return dedupe_strings(warnings)


def _title_for_route(
    retailer: str,
    cards: list[str],
    gift_percent: float,
    cashback_percent: float,
    price_match_targets: list[str],
    estimated_percent: float,
) -> str:
    if estimated_percent == 0:
        return "Cheapest deal only route"
    parts = []
    if gift_percent or cards:
        parts.append("gift card/points")
    if cashback_percent:
        parts.append("cashback")
    if price_match_targets:
        parts.append("price match")
    route = " + ".join(parts) if parts else "deal"
    return f"Best {route} stack for {retailer}"


def _score(percent: float, confidence: str, risk_level: str, sources: list[str], price: float | None) -> float:
    confidence_bonus = {"high": 4.0, "medium": 2.0, "low": 0.5}.get(confidence, 0.0)
    risk_penalty = {"low": 0.0, "medium": 1.5, "high": 4.0}.get(risk_level, 2.0)
    source_bonus = min(len(sources), 5) * 0.2
    price_bonus = 0.5 if price else 0.0
    return round(percent + confidence_bonus + source_bonus + price_bonus - risk_penalty, 2)


def _evidence(items: list[SourceItem]) -> list[dict[str, str]]:
    evidence = []
    for item in items:
        if not item.title:
            continue
        evidence.append({"source": item.source, "title": item.title, "url": item.url})
    return evidence


def _confidence_rank(value: Any) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(value), 0)


def _first(values):
    for value in values:
        if value:
            return value
    return None
