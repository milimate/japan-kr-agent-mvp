from __future__ import annotations

from typing import Any
from typing import Optional

from pydantic import BaseModel, Field


class RunLinkRequest(BaseModel):
    source_url: str = Field(..., description='일본 쇼핑몰 상품 링크')
    auto_publish: Optional[bool] = Field(
        default=None, description='None이면 서버 기본값 사용, true/false면 요청 기준'
    )


class RunLinkBatchRequest(BaseModel):
    source_urls: list[str] = Field(default_factory=list)
    auto_publish: Optional[bool] = None


class NaverRawPublishRequest(BaseModel):
    product_payload: dict[str, Any]


class NaverBuildPayloadRequest(BaseModel):
    title: str
    sale_price_krw: int
    template_hint: Optional[str] = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class NaverBuildPayloadResponse(BaseModel):
    payload: dict[str, Any]
    template_used: str
    validation_errors: list[str] = Field(default_factory=list)


class ProductExtraction(BaseModel):
    source_site: str
    source_url: str
    title: str
    source_price_jpy: int
    representative_image_url: Optional[str] = None


class PricingResult(BaseModel):
    fx_rate: float
    shipping_cost_krw: int
    market_fee_rate: float
    target_price_krw: int
    estimated_margin_rate: float


class PolicyResult(BaseModel):
    risk: str
    blocked: bool
    reasons: list[str]


class PublishResult(BaseModel):
    attempted: bool
    published: bool
    market_product_id: Optional[str] = None
    message: str


class RunLinkResponse(BaseModel):
    extraction: ProductExtraction
    pricing: PricingResult
    policy: PolicyResult
    approval_status: str
    publish_status: str
    publish_result: PublishResult
    notes: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


class RunLinkBatchResponse(BaseModel):
    results: list[RunLinkResponse] = Field(default_factory=list)
