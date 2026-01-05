"""
deal_agent.py
================

This script provides a simple foundation for building a deal-watching agent that
monitors OzBargain for new promotions and scores them according to basic
criteria.  It is designed as a starting point for experimentation; you can
extend it to integrate with other data sources (e.g. ShopBack, TopCashback,
FreePoints, GCDB) and to notify you via email or chat when promising deals
appear.

Limitations
-----------
* Internet access is required for this script to fetch live deal data from
  OzBargain.  The execution environment used by this assistant is isolated
  and cannot perform HTTP requests.  To run the script successfully, copy
  it to your own machine with an internet connection.
* The scraping logic may need to be updated if OzBargain changes its HTML
  structure.  Use browser developer tools to inspect the site and adjust the
  CSS selectors as needed.
* This version only implements basic scraping and scoring; there is no
  notification mechanism.  You can add functions to send alerts via email,
  Telegram, Slack, etc.  Refer to the README section at the bottom of this
  file for guidance.

Usage
-----
Run the script from the command line:

    python deal_agent.py

The script fetches the latest deals, filters them based on simple
keywords, scores them, and prints the top results.  Adjust the `KEYWORDS`,
`MERCHANTS` and scoring logic as needed.

"""

import datetime
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from bs4 import BeautifulSoup


# Define the merchants and keywords you care about.  You can customise these
# lists to suit your own interests.  The MERCHANTS list is used for
# quick matching; keywords help categorise deals (gift cards, cashback, points).
MERCHANTS = [
    "Amazon",
    "JB Hi-Fi",
    "Woolworths",
    "Coles",
    "Apple",
]

KEYWORDS = {
    "gift_card": ["gift card", "egift", "voucher"],
    "cashback": ["cashback", "cash back", "shopback", "topcash"],
    "points": ["points", "bonus points", "x points"],
    "coupon": ["coupon", "promo code", "discount code"],
}


@dataclass
class Deal:
    """Represents a single OzBargain deal entry."""

    title: str
    link: str
    merchant: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    score: float = 0.0

    def compute_score(self) -> None:
        """Compute a simple score based on tags and merchant.

        This scoring function is intentionally basic.  It assigns weight to
        gift card, cashback and points deals and slightly boosts deals that
        mention a merchant from the MERCHANTS list.  Adjust the weights as
        needed for your use case.
        """
        score = 0.0
        if "gift_card" in self.tags:
            score += 3.0
        if "cashback" in self.tags:
            score += 2.0
        if "points" in self.tags:
            score += 1.5
        if "coupon" in self.tags:
            score += 1.0
        if self.merchant:
            score += 1.0  # small boost for deals matching your merchants
        self.score = score


def fetch_ozbargain_deals(limit: int = 20) -> List[Deal]:
    """Fetch recent deals from OzBargain and return them as Deal objects.

    Parameters
    ----------
    limit : int, optional
        Maximum number of deals to return.  The default is 20.

    Returns
    -------
    List[Deal]
        A list of Deal objects with basic metadata extracted.
    """
    url = "https://www.ozbargain.com.au/deals"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    # OzBargain lists deals in <div class="node node-deal"> elements.
    deal_nodes = soup.select("div.node")
    deals: List[Deal] = []
    for node in deal_nodes:
        if len(deals) >= limit:
            break
        title_node = node.select_one("h2.title a")
        if not title_node:
            continue
        title = title_node.get_text(strip=True)
        link = title_node["href"]
        # Convert relative links to absolute URLs
        if link.startswith("/"):
            link = f"https://www.ozbargain.com.au{link}"
        deal = Deal(title=title, link=link)
        deal.merchant = extract_merchant(title)
        deal.tags = extract_tags(title)
        deal.compute_score()
        deals.append(deal)
    return deals


def extract_merchant(title: str) -> Optional[str]:
    """Return the first merchant name found in the title, if any."""
    lower_title = title.lower()
    for merchant in MERCHANTS:
        if merchant.lower() in lower_title:
            return merchant
    return None


def extract_tags(title: str) -> List[str]:
    """Return a list of tag identifiers found in the title based on KEYWORDS."""
    tags = []
    lower_title = title.lower()
    for tag_name, words in KEYWORDS.items():
        for word in words:
            if word in lower_title:
                tags.append(tag_name)
                break
    return tags


def main() -> None:
    """Entry point: fetch and display deals sorted by score."""
    try:
        deals = fetch_ozbargain_deals(limit=30)
    except Exception as e:
        print(f"Error fetching deals: {e}")
        return
    # Sort by score descending
    deals.sort(key=lambda d: d.score, reverse=True)
    print(f"\nTop {len(deals)} deals (sorted by score):\n")
    for i, deal in enumerate(deals, start=1):
        print(f"{i}. {deal.title}")
        print(f"   Link: {deal.link}")
        if deal.merchant:
            print(f"   Merchant: {deal.merchant}")
        if deal.tags:
            print(f"   Tags: {', '.join(deal.tags)}")
        print(f"   Score: {deal.score:.1f}\n")


if __name__ == "__main__":
    main()


# ----- README / Extension Notes -----

# The Deal class and associated helper functions provide a simple way to
# categorise and score deals.  When you expand the agent, consider
# persisting seen deals in a SQLite database and adding functions to send
# notifications via your preferred channel (email, Telegram, Slack).  For
# instance, you might use the 'smtplib' module to send an email when a deal
# exceeds a threshold score, or the 'python-telegram-bot' library to send a
# message to a Telegram chat.

# To integrate with other sources:
# * ShopBack / TopCashback: implement functions that scrape or use APIs
#   provided by those services to retrieve current cashback rates.  When
#   evaluating a deal, you can compute the effective savings by combining
#   portal cashback with any discount codes or gift card bonuses.
# * FreePoints: fetch current points promotions (e.g. 20x Everyday Rewards
#   points) and calculate their monetary value based on your valuation of
#   points.  Add an extra score component for points multipliers when a
#   merchant matches the promotion.
# * GCDB: retrieve information about gift card bonuses, typical ranges and
#   historical highs, so you know when a gift card deal is unusually good.

# Respect the terms of use for each website you access, including OzBargain.
# Always throttle your requests to avoid overloading the site, and cache
# responses when appropriate.  Consider using asynchronous requests or
# concurrency if you need to handle multiple sources quickly.