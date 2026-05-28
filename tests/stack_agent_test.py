import unittest

from fastapi.testclient import TestClient

import stack_chat_app
from stack_agent import StackAgent
from stack_agent.models import SourceItem
from stack_agent.text import compatible_gift_cards, detect_merchants


def rich_fake_collector(query, url=None, max_per_source=8):
    base = SourceItem(
        source="OzBargain",
        title="MacBook Air M4 13-inch $1499 at JB Hi-Fi - Click & Collect",
        url="https://www.ozbargain.com.au/node/123",
        kind="base_deal",
        retailer="JB Hi-Fi",
        price=1499.0,
        text="MacBook Air M4 13-inch $1499 at JB Hi-Fi - Click & Collect in stock",
    )
    points = SourceItem(
        source="FreePoints",
        title="20x Everyday Rewards points on Ultimate gift cards at Woolworths",
        url="https://freepoints.com.au/example",
        kind="points_offer",
        retailer="Woolworths",
        text="20x Everyday Rewards points on Ultimate gift cards at Woolworths",
    )
    gcdb = SourceItem(
        source="GCDB",
        title="Ultimate gift cards can be used at JB Hi-Fi",
        url="https://gcdb.com.au/merchants/",
        kind="gift_card_offer",
        retailer="JB Hi-Fi",
        text="Ultimate gift cards can be used at JB Hi-Fi",
    )
    cashback = SourceItem(
        source="ShopBack",
        title="JB Hi-Fi up to 2.5% cashback",
        url="https://www.shopback.com.au/jb-hi-fi",
        kind="cashback_offer",
        retailer="JB Hi-Fi",
        text="JB Hi-Fi up to 2.5% cashback",
        metadata={"percent": 2.5},
    )
    if url:
        base.metadata["input_url"] = True
        base.url = url
    return [base, points, gcdb, cashback], []


class StackAgentUnitTests(unittest.TestCase):
    def test_detects_supported_merchants(self):
        text = "Apple at Officeworks, JB Hifi, The Good Guys, Harvey Norman, Amazon, Costco, Coles and Woolies"
        merchants = detect_merchants(text)
        for merchant in [
            "Apple",
            "Officeworks",
            "JB Hi-Fi",
            "The Good Guys",
            "Harvey Norman",
            "Amazon",
            "Costco",
            "Coles",
            "Woolworths",
        ]:
            self.assertIn(merchant, merchants)

    def test_gift_card_routes_cover_major_card_types(self):
        self.assertIn("Apple Gift Card", compatible_gift_cards("Apple"))
        self.assertIn("Ultimate Gift Card", compatible_gift_cards("JB Hi-Fi"))
        self.assertIn("TCN Gift Card", compatible_gift_cards("The Good Guys"))
        self.assertIn("Super Swap", compatible_gift_cards("Amazon"))
        self.assertIn("Prezee", compatible_gift_cards("Officeworks"))
        self.assertIn("Amazon Gift Card", compatible_gift_cards("Amazon"))

    def test_macbook_query_returns_aggressive_stack(self):
        agent = StackAgent(source_collector=rich_fake_collector)
        result = agent.search("MacBook Air M4", max_results=3).to_dict()

        rec = result["recommendations"][0]
        self.assertEqual(rec["retailer"], "JB Hi-Fi")
        self.assertGreaterEqual(rec["estimated_saving"]["percent"], 12.0)
        self.assertEqual(rec["risk_level"], "high")
        self.assertIn("FreePoints", rec["sources"])
        self.assertIn("ShopBack", rec["sources"])
        self.assertTrue(any("gift card" in step.lower() for step in rec["stack_steps"]))
        self.assertTrue(any("cashback" in warning.lower() for warning in rec["warnings"]))

    def test_product_url_input_is_used_as_base_deal(self):
        agent = StackAgent(source_collector=rich_fake_collector)
        result = agent.search("MacBook Air M4", url="https://www.jbhifi.com.au/product/macbook", max_results=1).to_dict()
        rec = result["recommendations"][0]
        self.assertEqual(rec["base_deal"]["url"], "https://www.jbhifi.com.au/product/macbook")

    def test_no_stack_case_returns_fallback_style_recommendation(self):
        def empty_collector(query, url=None, max_per_source=8):
            return [], []

        agent = StackAgent(source_collector=empty_collector)
        result = agent.search("obscure product", max_results=1).to_dict()
        rec = result["recommendations"][0]
        self.assertEqual(rec["estimated_saving"]["percent"], 0.0)
        self.assertTrue(any("No-stack" in warning for warning in rec["warnings"]))

    def test_partial_source_failure_is_reported(self):
        def partial_collector(query, url=None, max_per_source=8):
            items, _ = rich_fake_collector(query, url, max_per_source)
            return items, ["GCDB failed: timeout"]

        agent = StackAgent(source_collector=partial_collector)
        result = agent.search("iPad Air", max_results=1).to_dict()
        self.assertEqual(result["source_errors"], ["GCDB failed: timeout"])

    def test_malformed_url_is_rejected(self):
        agent = StackAgent(source_collector=rich_fake_collector)
        with self.assertRaises(ValueError):
            agent.search("iPad Air", url="file:///tmp/item.html")


class StackAgentApiTests(unittest.TestCase):
    def setUp(self):
        self.original_agent = stack_chat_app.agent
        stack_chat_app.agent = StackAgent(source_collector=rich_fake_collector)
        self.client = TestClient(stack_chat_app.app)

    def tearDown(self):
        stack_chat_app.agent = self.original_agent

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_stack_search_endpoint_success(self):
        response = self.client.post(
            "/api/stack-search",
            json={"query": "MacBook Air M4", "max_results": 2},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "MacBook Air M4")
        self.assertTrue(body["recommendations"])

    def test_stack_search_endpoint_rejects_bad_url(self):
        response = self.client.post(
            "/api/stack-search",
            json={"query": "iPad Air", "url": "ftp://example.com/item"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
