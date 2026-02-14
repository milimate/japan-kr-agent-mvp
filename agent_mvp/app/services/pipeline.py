from __future__ import annotations

from typing import Optional

from app.config import settings
from app.policies import evaluate_policy
from app.schemas import (
    NaverBuildPayloadResponse,
    PolicyResult,
    PricingResult,
    ProductExtraction,
    PublishResult,
    RunLinkBatchResponse,
    RunLinkResponse,
)
from app.services.llm_client import LLMClient
from app.services.naver_payload_builder import NaverPayloadBuilder
from app.tools.base import MarketPublishPayload
from app.tools.naver_market import NaverMarketPublisher


class LinkPipelineService:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.publisher = NaverMarketPublisher()
        self.payload_builder = NaverPayloadBuilder()

    def run(self, source_url: str, auto_publish: Optional[bool] = None) -> RunLinkResponse:
        extracted = self.llm.extract_product_from_link(source_url)
        should_auto_publish = settings.auto_publish_on_run_link if auto_publish is None else auto_publish

        extraction = ProductExtraction(
            source_site=extracted['source_site'],
            source_url=extracted['source_url'],
            title=extracted['title'],
            source_price_jpy=extracted['source_price_jpy'],
            representative_image_url=extracted.get('representative_image_url'),
        )

        pricing = self._calculate_price(extraction.source_price_jpy)
        policy_decision = evaluate_policy(extraction.title)
        policy = PolicyResult(
            risk=policy_decision.risk,
            blocked=policy_decision.blocked,
            reasons=policy_decision.reasons,
        )

        approval_status = self._decide_approval(policy.blocked, pricing.estimated_margin_rate)

        publish_result = PublishResult(
            attempted=False,
            published=False,
            market_product_id=None,
            message='승인 전 또는 자동발행 비활성',
        )
        publish_status = 'draft'

        if approval_status == 'approved' and should_auto_publish:
            overrides = {}
            if extraction.representative_image_url:
                overrides = {
                    "originProduct": {
                        "images": [{"url": extraction.representative_image_url}]
                    }
                }
            product_payload, payload_errors, template_used = self.payload_builder.build(
                title=extraction.title,
                sale_price_krw=pricing.target_price_krw,
                overrides=overrides,
            )
            if payload_errors:
                return RunLinkResponse(
                    extraction=extraction,
                    pricing=pricing,
                    policy=policy,
                    approval_status=approval_status,
                    publish_status='error',
                    publish_result=PublishResult(
                        attempted=True,
                        published=False,
                        market_product_id=None,
                        message='네이버 payload 필수값 누락: ' + "; ".join(payload_errors),
                    ),
                    notes=[extracted.get('note', '')],
                    debug={
                        'min_margin_rate': settings.min_margin_rate,
                        'auto_publish': should_auto_publish,
                        'naver_use_real_api': settings.naver_use_real_api,
                        'template_used': template_used,
                    },
                )
            market_res = self.publisher.publish(
                MarketPublishPayload(
                    source_url=extraction.source_url,
                    title=extraction.title,
                    target_price_krw=pricing.target_price_krw,
                    risk=policy.risk,
                    product_payload=product_payload,
                )
            )
            publish_result = PublishResult(
                attempted=True,
                published=market_res.success,
                market_product_id=market_res.market_product_id,
                message=market_res.message,
            )
            publish_status = 'published' if market_res.success else 'error'

        return RunLinkResponse(
            extraction=extraction,
            pricing=pricing,
            policy=policy,
            approval_status=approval_status,
            publish_status=publish_status,
            publish_result=publish_result,
            notes=[extracted.get('note', '')],
            debug={
                'min_margin_rate': settings.min_margin_rate,
                'auto_publish': should_auto_publish,
                'naver_use_real_api': settings.naver_use_real_api,
            },
        )

    def run_batch(
        self, source_urls: list[str], auto_publish: Optional[bool] = None
    ) -> RunLinkBatchResponse:
        cleaned = [u.strip() for u in source_urls if u and u.strip()]
        results = [self.run(url, auto_publish=auto_publish) for url in cleaned]
        return RunLinkBatchResponse(results=results)

    def _calculate_price(self, source_price_jpy: int) -> PricingResult:
        cost_krw = round(source_price_jpy * settings.default_fx_rate + settings.default_shipping_cost_krw)
        target_price = round(cost_krw * (1 + settings.default_markup_rate))
        fee = target_price * settings.default_market_fee_rate
        margin = target_price - cost_krw - fee
        margin_rate = margin / target_price if target_price > 0 else 0

        return PricingResult(
            fx_rate=settings.default_fx_rate,
            shipping_cost_krw=settings.default_shipping_cost_krw,
            market_fee_rate=settings.default_market_fee_rate,
            target_price_krw=target_price,
            estimated_margin_rate=round(margin_rate, 4),
        )

    def _decide_approval(self, blocked: bool, margin_rate: float) -> str:
        if blocked:
            return 'rejected'
        if margin_rate < settings.min_margin_rate:
            return 'rejected'
        return 'approved'

    def publish_naver_raw(self, payload: dict) -> PublishResult:
        market_res = self.publisher.publish(
            MarketPublishPayload(
                source_url='manual_raw_payload',
                title='manual_raw_payload',
                target_price_krw=0,
                risk='manual',
                product_payload=payload,
            )
        )
        return PublishResult(
            attempted=True,
            published=market_res.success,
            market_product_id=market_res.market_product_id,
            message=market_res.message,
        )

    def build_naver_payload(
        self, title: str, sale_price_krw: int, overrides: dict, template_hint: Optional[str]
    ) -> NaverBuildPayloadResponse:
        payload, errors, template_used = self.payload_builder.build(
            title=title,
            sale_price_krw=sale_price_krw,
            overrides=overrides,
            template_hint=template_hint,
        )
        return NaverBuildPayloadResponse(
            payload=payload,
            template_used=template_used,
            validation_errors=errors,
        )
