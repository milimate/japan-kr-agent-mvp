from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    app_name: str = 'Japan KR Agent MVP'
    env: str = 'dev'
    openai_api_key: Optional[str] = None
    openai_model: str = 'gpt-4.1-mini'
    llm_enabled: bool = True

    default_markup_rate: float = 0.35
    min_margin_rate: float = 0.15
    default_fx_rate: float = 9.2
    default_shipping_cost_krw: int = 9000
    default_market_fee_rate: float = 0.13

    auto_publish: bool = False
    auto_publish_on_run_link: bool = True
    market_channel: str = 'naver'
    naver_client_id: Optional[str] = None
    naver_client_secret: Optional[str] = None
    naver_account_id: Optional[str] = None
    naver_api_base_url: str = 'https://api.commerce.naver.com/external'
    naver_token_type: str = 'SELLER'
    naver_product_create_path: str = '/v2/products'
    naver_use_real_api: bool = False
    naver_default_leaf_category_id: int = 50000000
    naver_default_representative_image_url: Optional[str] = None
    naver_default_optional_image_urls: str = ''
    naver_default_origin_area_code: str = '02'
    naver_default_importer: str = '구매대행'
    naver_default_after_service_guide: str = '채팅문의'
    naver_default_after_service_tel: str = '010-0000-0000'
    naver_default_detail_content_html: str = '<p>상세 설명 준비 중</p>'
    naver_default_notice_type: str = 'FASHION_ITEMS'
    naver_payload_template_mode: str = 'auto'


settings = Settings()
