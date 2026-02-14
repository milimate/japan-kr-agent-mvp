from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Optional


@dataclass
class MarketPublishPayload:
    source_url: str
    title: str
    target_price_krw: int
    risk: str
    product_payload: Optional[dict[str, Any]] = None


@dataclass
class MarketPublishResponse:
    success: bool
    market_product_id: Optional[str]
    message: str
