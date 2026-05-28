"""OpenAI tool-calling agent for live stack search.

Wraps the existing SourceClient scrapers and StackAgent scoring engine as
OpenAI function tools, plus uses OpenAI's hosted web_search tool to cover
sites the scrapers don't reach (Cashrewards, Prezzee, retailer cashback pages).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import Any

from .engine import StackAgent
from .models import SourceItem
from .sources import SourceClient


DEFAULT_MODEL = os.environ.get("OPENAI_STACK_MODEL", "gpt-4o-mini")
MAX_TOOL_ITERATIONS = 8
CACHE_TTL_SECONDS = 900  # 15 min

SYSTEM_PROMPT = """You are an Australian deal-stacking assistant. The user wants to maximise total return when buying a product or topping up a wallet by combining:
- A base deal or sale (OzBargain, retailer page)
- Discounted gift cards (GCDB, Prezzee, Coles/Woolworths Ultimate/TCN)
- Bonus points promos (Flybuys, Everyday Rewards, Qantas, Velocity)
- Cashback portals (Cashrewards, ShopBack, TopCashback)
- Credit card / BNPL offers when relevant

Always:
1. Use the provided tools to fetch LIVE data. Never invent percentages, deals, or URLs.
2. Call multiple tools in parallel when possible to cover all stack layers.
3. Use `web_search` for sites the scrapers don't cover (Cashrewards, Prezzee, retailer cashback) or when scraper tools return empty results.
4. After gathering evidence, call `score_stack` once to get a structured recommendation, then synthesise a final answer that:
   - Lists the concrete stack steps in order
   - Shows the effective % saving and dollar saving with assumptions
   - Names the risk level (stock, expiry, T&Cs)
   - Cites every source URL inline as [domain](url)
5. Be concise. No marketing fluff. Australian context, AUD only.
6. If nothing stackable is found, say so honestly."""


@dataclass
class AgentEvent:
    """Stream event emitted to the UI."""
    type: str   # "status" | "tool_call" | "tool_result" | "delta" | "final" | "error"
    data: Any

    def to_sse(self) -> str:
        payload = json.dumps({"type": self.type, "data": self.data})
        return f"data: {payload}\n\n"


class _TTLCache:
    def __init__(self, ttl: int = CACHE_TTL_SECONDS):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)


def _item_to_dict(item: SourceItem) -> dict[str, Any]:
    d = asdict(item)
    # Trim large text blobs the model doesn't need
    if d.get("text") and len(d["text"]) > 400:
        d["text"] = d["text"][:400] + "..."
    return d


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_ozbargain",
        "description": "Search OzBargain.com.au for live deals matching a product or retailer query. Returns deal titles, URLs, prices.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Product or retailer keyword, e.g. 'MacBook Air', 'JB Hi-Fi'"},
                "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 15},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "search_gift_cards",
        "description": "Search GCDB (Australian gift card database) for current discounted gift card offers. Use to find Ultimate/TCN/retailer-specific gift card discounts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 15},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "search_points_promos",
        "description": "Search FreePoints.com.au for bonus points promotions (Flybuys, Everyday Rewards, Qantas, Velocity).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 15},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "search_cashback",
        "description": "Search ShopBack and TopCashback for current cashback rates at a retailer. For Cashrewards or other portals not covered here, use web_search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "retailer": {"type": "string", "description": "Optional specific retailer name to narrow the search"},
                "limit": {"type": "integer", "default": 6, "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "fetch_url",
        "description": "Fetch and extract the title/text of any product or deal URL provided by the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full https URL"},
                "query": {"type": "string", "description": "Context query for relevance matching", "default": ""},
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "score_stack",
        "description": "Run the in-house scoring engine over the user's query (and optional URL) to get structured stack recommendations with effective savings, risk, and warnings. Call this AFTER gathering tool evidence to get the canonical recommendation, then summarise it.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "url": {"type": "string"},
                "max_results": {"type": "integer", "default": 3, "minimum": 1, "maximum": 5},
            },
            "required": ["query"],
        },
    },
    # OpenAI hosted tool — does live Bing-backed web search with citations.
    {"type": "web_search"},
]


class AIStackAgent:
    """OpenAI tool-calling wrapper around the deal-stack scrapers + engine."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        client: Any | None = None,
    ):
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key and client is None:
            raise RuntimeError("OPENAI_API_KEY is not set. Export it or pass api_key=.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package not installed. Run: pip install openai") from exc

        self.model = model
        self.client = client or OpenAI(api_key=api_key)
        self.source_client = SourceClient()
        self.stack_agent = StackAgent()
        self.cache = _TTLCache()

    # ---- tool dispatch -------------------------------------------------

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            if name == "search_ozbargain":
                items = self.source_client.search_ozbargain(args["query"], args.get("limit", 8))
                result = [_item_to_dict(i) for i in items]
            elif name == "search_gift_cards":
                items = self.source_client.search_gcdb(args["query"], args.get("limit", 10))
                result = [_item_to_dict(i) for i in items]
            elif name == "search_points_promos":
                items = self.source_client.search_freepoints(args["query"], args.get("limit", 10))
                result = [_item_to_dict(i) for i in items]
            elif name == "search_cashback":
                items = self.source_client.search_cashback(
                    args["query"], retailer=args.get("retailer"), limit=args.get("limit", 6)
                )
                result = [_item_to_dict(i) for i in items]
            elif name == "fetch_url":
                item = self.source_client.item_from_url(args["url"], args.get("query", ""))
                result = _item_to_dict(item) if item else None
            elif name == "score_stack":
                res = self.stack_agent.search(
                    args["query"], url=args.get("url"), max_results=args.get("max_results", 3)
                )
                result = res.to_dict()
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"{name} failed: {exc}"}

        self.cache.set(cache_key, result)
        return result

    # ---- main loop -----------------------------------------------------

    def run_stream(self, user_query: str, url: str | None = None) -> Iterator[AgentEvent]:
        """Run the agent and yield streaming events for SSE."""
        user_msg = user_query.strip()
        if url:
            user_msg += f"\n\nInput URL: {url}"
        if not user_msg:
            yield AgentEvent("error", "Empty query")
            return

        input_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        yield AgentEvent("status", f"Starting agent with model {self.model}")

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=input_messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except Exception as exc:  # noqa: BLE001
                yield AgentEvent("error", f"OpenAI call failed: {exc}")
                return

            tool_calls: list[Any] = []
            assistant_text_parts: list[str] = []

            for item in response.output:
                input_messages.append(item.model_dump() if hasattr(item, "model_dump") else item)
                item_type = getattr(item, "type", None)
                if item_type == "function_call":
                    tool_calls.append(item)
                elif item_type == "message":
                    for part in getattr(item, "content", []) or []:
                        text = getattr(part, "text", None)
                        if text:
                            assistant_text_parts.append(text)
                elif item_type == "web_search_call":
                    yield AgentEvent("tool_call", {"name": "web_search", "args": {}})

            if not tool_calls:
                final = "\n".join(assistant_text_parts).strip() or "(no answer produced)"
                yield AgentEvent("final", final)
                return

            for call in tool_calls:
                name = call.name
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield AgentEvent("tool_call", {"name": name, "args": args})

                result = self._dispatch_tool(name, args)

                preview: Any
                if isinstance(result, list):
                    preview = f"{len(result)} items"
                elif isinstance(result, dict) and "recommendations" in result:
                    preview = f"{len(result.get('recommendations', []))} recommendations"
                else:
                    preview = "ok" if result else "empty"
                yield AgentEvent("tool_result", {"name": name, "preview": preview})

                input_messages.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, default=str)[:8000],
                })

        yield AgentEvent("error", f"Hit max tool iterations ({MAX_TOOL_ITERATIONS})")

    def run(self, user_query: str, url: str | None = None) -> dict[str, Any]:
        """Non-streaming convenience: collect all events and return final answer."""
        events: list[dict[str, Any]] = []
        final = ""
        for event in self.run_stream(user_query, url):
            events.append({"type": event.type, "data": event.data})
            if event.type == "final":
                final = event.data
            elif event.type == "error":
                final = f"Error: {event.data}"
        return {"answer": final, "events": events}
