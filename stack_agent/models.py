"""Shared data models for the deal-stacking agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class SourceItem:
    source: str
    title: str
    url: str
    kind: str = "deal"
    retailer: str | None = None
    price: float | None = None
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class StackRecommendation:
    title: str
    retailer: str
    base_deal: dict[str, Any]
    stack_steps: list[str]
    estimated_saving: dict[str, Any]
    risk_level: str
    warnings: list[str]
    sources: list[str]
    score: float
    evidence: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class StackSearchResult:
    query: str
    recommendations: list[StackRecommendation]
    source_errors: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "recommendations": [
                {
                    "title": rec.title,
                    "retailer": rec.retailer,
                    "base_deal": rec.base_deal,
                    "stack_steps": rec.stack_steps,
                    "estimated_saving": rec.estimated_saving,
                    "risk_level": rec.risk_level,
                    "warnings": rec.warnings,
                    "sources": rec.sources,
                    "score": rec.score,
                    "evidence": rec.evidence,
                }
                for rec in self.recommendations
            ],
            "source_errors": self.source_errors,
            "generated_at": self.generated_at,
        }
