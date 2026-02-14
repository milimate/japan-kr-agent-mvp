from __future__ import annotations

from fastapi import FastAPI
from app.config import settings
from app.schemas import (
    NaverBuildPayloadRequest,
    NaverBuildPayloadResponse,
    NaverRawPublishRequest,
    PublishResult,
    RunLinkBatchRequest,
    RunLinkBatchResponse,
    RunLinkRequest,
    RunLinkResponse,
)
from app.services.pipeline import LinkPipelineService


app = FastAPI(title=settings.app_name)
service = LinkPipelineService()


@app.get('/health')
def health() -> dict:
    return {'status': 'ok', 'env': settings.env}


@app.post('/run-link', response_model=RunLinkResponse)
def run_link(req: RunLinkRequest) -> RunLinkResponse:
    return service.run(req.source_url, auto_publish=req.auto_publish)


@app.post('/run-link-batch', response_model=RunLinkBatchResponse)
def run_link_batch(req: RunLinkBatchRequest) -> RunLinkBatchResponse:
    return service.run_batch(req.source_urls, auto_publish=req.auto_publish)


@app.post('/naver/publish-raw', response_model=PublishResult)
def publish_naver_raw(req: NaverRawPublishRequest) -> PublishResult:
    return service.publish_naver_raw(req.product_payload)


@app.post('/naver/build-payload', response_model=NaverBuildPayloadResponse)
def build_naver_payload(req: NaverBuildPayloadRequest) -> NaverBuildPayloadResponse:
    return service.build_naver_payload(
        title=req.title,
        sale_price_krw=req.sale_price_krw,
        overrides=req.overrides,
        template_hint=req.template_hint,
    )
