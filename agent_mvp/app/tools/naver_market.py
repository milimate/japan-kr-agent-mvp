from __future__ import annotations

import hashlib
from typing import Any
from typing import Optional

from app.config import settings
from app.services.naver_client import NaverApiError, NaverAuthError, NaverClient
from app.tools.base import MarketPublishPayload, MarketPublishResponse


class NaverMarketPublisher:
    def __init__(self) -> None:
        self.client = NaverClient()

    def publish(self, payload: MarketPublishPayload) -> MarketPublishResponse:
        if settings.naver_use_real_api:
            return self._publish_real(payload)
        return self._publish_mock(payload)

    def _publish_mock(self, payload: MarketPublishPayload) -> MarketPublishResponse:
        # MVP 단계: 네이버 실연동 전 mock 응답
        key = f"{payload.source_url}|{payload.title}|{payload.target_price_krw}"
        pid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return MarketPublishResponse(
            success=True,
            market_product_id=f"naver_mock_{pid}",
            message="네이버 마켓 MVP mock publish 성공",
        )

    def _publish_real(self, payload: MarketPublishPayload) -> MarketPublishResponse:
        product_payload = payload.product_payload
        if not product_payload:
            return MarketPublishResponse(
                success=False,
                market_product_id=None,
                message="실연동 모드는 product_payload가 필요합니다.",
            )

        try:
            res = self.client.create_product(product_payload)
            market_id = self._extract_product_id(res)
            return MarketPublishResponse(
                success=True,
                market_product_id=market_id,
                message="네이버 상품 등록 성공",
            )
        except (NaverAuthError, NaverApiError) as e:
            return MarketPublishResponse(
                success=False,
                market_product_id=None,
                message=str(e),
            )

    def _extract_product_id(self, payload: dict[str, Any]) -> Optional[str]:
        # 실제 응답 키는 API 버전에 따라 다를 수 있어 후보 키를 순서대로 확인
        for key in ("productNo", "id", "originProductNo"):
            v = payload.get(key)
            if v is not None:
                return str(v)
        return None
