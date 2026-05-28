"""Live source collectors for the stack agent."""

from __future__ import annotations

from urllib.parse import quote, quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from .models import SourceItem
from .text import (
    detect_cashback_portals,
    detect_gift_cards,
    detect_merchants,
    extract_domain,
    extract_percent,
    extract_price,
    is_http_url,
    norm,
    retailer_from_url,
    text_matches_query,
)


USER_AGENT = "DealStackAgent/1.0 (+https://github.com/Mayankv2001/daily_deal)"
DEFAULT_TIMEOUT = 12


class SourceClient:
    """Small live HTML client with source-specific extraction helpers."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch_html(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def item_from_url(self, url: str, query: str) -> SourceItem | None:
        if not is_http_url(url):
            raise ValueError("Only http and https product/deal URLs are supported.")
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "lxml")
        title = _best_page_title(soup) or url
        text = norm(f"{title} {soup.get_text(' ', strip=True)[:1200]}")
        domain = extract_domain(url)
        retailer = retailer_from_url(url) or _first(detect_merchants(text))
        source = _source_name_from_domain(domain)
        return SourceItem(
            source=source,
            title=title,
            url=url,
            kind="base_deal",
            retailer=retailer,
            price=extract_price(text),
            text=text,
            metadata={"input_url": True, "query_match": text_matches_query(text, query)},
        )

    def search_ozbargain(self, query: str, limit: int = 8) -> list[SourceItem]:
        urls = [
            f"https://www.ozbargain.com.au/search/node/{quote(query)}",
            f"https://www.ozbargain.com.au/search/node?keys={quote_plus(query)}",
        ]
        items: list[SourceItem] = []
        for url in urls:
            try:
                html = self.fetch_html(url)
            except requests.RequestException:
                continue
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.select("a[href^='/node/']"):
                title = norm(anchor.get_text(" ", strip=True))
                if len(title) < 8:
                    continue
                href = anchor.get("href") or ""
                full_url = urljoin("https://www.ozbargain.com.au/", href)
                context = norm(_nearby_text(anchor))
                combined = norm(f"{title} {context}")
                if not text_matches_query(combined, query) and len(items) >= 3:
                    continue
                items.append(
                    SourceItem(
                        source="OzBargain",
                        title=title,
                        url=full_url,
                        kind="base_deal",
                        retailer=_first(detect_merchants(combined)),
                        price=extract_price(combined),
                        text=combined,
                        metadata={"search_url": url},
                    )
                )
                if len(items) >= limit:
                    return _dedupe_items(items)
        return _dedupe_items(items)[:limit]

    def search_gcdb(self, query: str, limit: int = 12) -> list[SourceItem]:
        urls = [
            "https://gcdb.com.au/",
            "https://gcdb.com.au/resources/",
            "https://gcdb.com.au/merchants/",
            "https://gcdb.com.au/multi-retailer/",
            "https://gcdb.com.au/gift-card-offers/",
        ]
        items: list[SourceItem] = []
        for url in urls:
            html = self.fetch_html(url)
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.select("a[href]"):
                title = norm(anchor.get_text(" ", strip=True))
                href = anchor.get("href") or ""
                if len(title) < 5:
                    continue
                full_url = urljoin(url, href)
                if "gcdb.com.au" not in full_url:
                    continue
                context = norm(_nearby_text(anchor))
                combined = norm(f"{title} {context}")
                if not _looks_like_gcdb_signal(combined, query):
                    continue
                items.append(
                    SourceItem(
                        source="GCDB",
                        title=title,
                        url=full_url,
                        kind="gift_card_offer",
                        retailer=_first(detect_merchants(combined)),
                        price=None,
                        text=combined,
                        metadata={
                            "gift_cards": detect_gift_cards(combined),
                            "percent": extract_percent(combined),
                            "resource_url": url,
                        },
                    )
                )
                if len(items) >= limit:
                    return _dedupe_items(items)
        return _dedupe_items(items)[:limit]

    def search_freepoints(self, query: str, limit: int = 12) -> list[SourceItem]:
        urls = [
            "https://freepoints.com.au/",
            "https://freepoints.com.au/all/",
            "https://freepoints.com.au/gift-card-history/",
        ]
        items: list[SourceItem] = []
        for url in urls:
            html = self.fetch_html(url)
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.select("a[href]"):
                title = norm(anchor.get_text(" ", strip=True))
                href = anchor.get("href") or ""
                if len(title) < 5:
                    continue
                full_url = urljoin(url, href)
                if "freepoints.com.au" not in full_url:
                    continue
                context = norm(_nearby_text(anchor))
                combined = norm(f"{title} {context}")
                if not _looks_like_points_signal(combined, query):
                    continue
                items.append(
                    SourceItem(
                        source="FreePoints",
                        title=title,
                        url=full_url,
                        kind="points_offer",
                        retailer=_first(detect_merchants(combined)),
                        price=None,
                        text=combined,
                        metadata={"gift_cards": detect_gift_cards(combined), "resource_url": url},
                    )
                )
                if len(items) >= limit:
                    return _dedupe_items(items)
        return _dedupe_items(items)[:limit]

    def search_cashback(self, query: str, retailer: str | None = None, limit: int = 6) -> list[SourceItem]:
        search_term = retailer or query
        urls = [
            ("ShopBack", f"https://www.shopback.com.au/search?keyword={quote_plus(search_term)}"),
            ("TopCashback", f"https://www.topcashback.com.au/search/merchants/?s={quote_plus(search_term)}"),
        ]
        items: list[SourceItem] = []
        for portal, url in urls:
            html = self.fetch_html(url)
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.select("a[href]"):
                title = norm(anchor.get_text(" ", strip=True))
                if len(title) < 3:
                    continue
                context = norm(_nearby_text(anchor))
                combined = norm(f"{title} {context}")
                if not _looks_like_cashback_signal(combined, query, retailer):
                    continue
                items.append(
                    SourceItem(
                        source=portal,
                        title=title,
                        url=urljoin(url, anchor.get("href") or ""),
                        kind="cashback_offer",
                        retailer=retailer or _first(detect_merchants(combined)),
                        price=None,
                        text=combined,
                        metadata={
                            "portals": detect_cashback_portals(combined) or [portal],
                            "percent": extract_percent(combined),
                            "search_url": url,
                        },
                    )
                )
                if len(items) >= limit:
                    return _dedupe_items(items)
        return _dedupe_items(items)[:limit]


def collect_live_sources(
    query: str,
    url: str | None = None,
    max_per_source: int = 8,
    client: SourceClient | None = None,
) -> tuple[list[SourceItem], list[str]]:
    client = client or SourceClient()
    items: list[SourceItem] = []
    errors: list[str] = []

    if url:
        try:
            item = client.item_from_url(url, query)
            if item:
                items.append(item)
        except Exception as exc:  # noqa: BLE001 - surface partial-source failures to callers
            errors.append(f"Input URL failed: {exc}")

    source_calls = [
        ("OzBargain", lambda: client.search_ozbargain(query, max_per_source)),
        ("GCDB", lambda: client.search_gcdb(query, max_per_source)),
        ("FreePoints", lambda: client.search_freepoints(query, max_per_source)),
    ]
    for source, call in source_calls:
        try:
            items.extend(call())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source} failed: {exc}")

    retailer = _first([item.retailer for item in items if item.retailer])
    try:
        items.extend(client.search_cashback(query, retailer=retailer, limit=max_per_source))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Cashback search failed: {exc}")

    return _dedupe_items(items), errors


def _best_page_title(soup: BeautifulSoup) -> str:
    og_title = soup.select_one("meta[property='og:title']")
    if og_title and og_title.get("content"):
        return norm(og_title["content"])
    h1 = soup.select_one("h1")
    if h1:
        return norm(h1.get_text(" ", strip=True))
    if soup.title:
        return norm(soup.title.get_text(" ", strip=True))
    return ""


def _nearby_text(anchor) -> str:
    parent = anchor.find_parent(["article", "li", "tr", "div"])
    if parent:
        return parent.get_text(" ", strip=True)
    return anchor.get_text(" ", strip=True)


def _looks_like_gcdb_signal(text: str, query: str) -> bool:
    lower = text.lower()
    signal = any(term in lower for term in ["gift card", "giftcard", "ultimate", "tcn", "prezee", "swap", "offer", "merchant"])
    return signal and (text_matches_query(text, query) or any(card in lower for card in ["ultimate", "tcn", "apple", "amazon"]))


def _looks_like_points_signal(text: str, query: str) -> bool:
    lower = text.lower()
    signal = any(term in lower for term in ["points", "flybuys", "everyday rewards", "qantas", "velocity", "gift card", "giftcard"])
    return signal and (text_matches_query(text, query) or "gift" in lower or "points" in lower)


def _looks_like_cashback_signal(text: str, query: str, retailer: str | None) -> bool:
    lower = text.lower()
    if retailer and retailer.lower() in lower:
        return True
    if text_matches_query(text, query) and any(term in lower for term in ["cashback", "%", "shopback", "topcashback"]):
        return True
    return False


def _source_name_from_domain(domain: str) -> str:
    if "ozbargain.com.au" in domain:
        return "OzBargain"
    if "gcdb.com.au" in domain:
        return "GCDB"
    if "freepoints.com.au" in domain:
        return "FreePoints"
    if "shopback.com.au" in domain:
        return "ShopBack"
    if "topcashback.com.au" in domain:
        return "TopCashback"
    return domain or "Input URL"


def _dedupe_items(items: list[SourceItem]) -> list[SourceItem]:
    seen: set[tuple[str, str]] = set()
    out: list[SourceItem] = []
    for item in items:
        key = (item.source, item.url or item.title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _first(values):
    for value in values:
        if value:
            return value
    return None
