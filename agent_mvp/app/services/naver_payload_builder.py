from __future__ import annotations

from copy import deepcopy
from typing import Any
from typing import Optional

from app.config import settings

NOTICE_KEYS = {
    "FASHION_ITEMS": "fashionItems",
    "LIVING": "living",
    "DIGITAL_CONTENTS": "digitalContents",
}


class NaverPayloadBuilder:
    def build(
        self,
        *,
        title: str,
        sale_price_krw: int,
        overrides: Optional[dict[str, Any]] = None,
        template_hint: Optional[str] = None,
    ) -> tuple[dict[str, Any], list[str], str]:
        template_used = self._resolve_template_type(title=title, template_hint=template_hint)
        payload = self._base_payload(
            title=title,
            sale_price_krw=sale_price_krw,
            template_type=template_used,
        )
        if overrides:
            payload = self._deep_merge(payload, overrides)
        errors = self._validate_required(payload, template_used)
        return payload, errors, template_used

    def _resolve_template_type(self, *, title: str, template_hint: Optional[str]) -> str:
        if template_hint:
            hint = template_hint.strip().upper()
            if hint in NOTICE_KEYS:
                return hint

        mode = settings.naver_payload_template_mode.strip().lower()
        if mode != "auto":
            fixed = mode.upper()
            if fixed in NOTICE_KEYS:
                return fixed

        return self._infer_template_type_by_title(title)

    def _infer_template_type_by_title(self, title: str) -> str:
        t = title.lower()
        digital_hits = ["이어폰", "헤드셋", "케이블", "충전기", "모니터", "키보드", "마우스", "전자", "digital"]
        living_hits = ["컵", "접시", "냄비", "수납", "침구", "생활", "주방", "욕실", "living"]
        fashion_hits = ["티셔츠", "바지", "원피스", "가방", "신발", "패션", "의류", "fashion"]

        if any(k in t for k in digital_hits):
            return "DIGITAL_CONTENTS"
        if any(k in t for k in living_hits):
            return "LIVING"
        if any(k in t for k in fashion_hits):
            return "FASHION_ITEMS"
        return settings.naver_default_notice_type.strip().upper() or "FASHION_ITEMS"

    def _base_payload(self, *, title: str, sale_price_krw: int, template_type: str) -> dict[str, Any]:
        rep_image_url = settings.naver_default_representative_image_url or ""
        optional_urls = [
            u.strip()
            for u in settings.naver_default_optional_image_urls.split(",")
            if u.strip()
        ]
        images = [{"url": rep_image_url}] if rep_image_url else []
        for u in optional_urls:
            images.append({"url": u})

        notice_key = NOTICE_KEYS.get(template_type, "fashionItems")
        notice_block = self._notice_block_for_template(template_type)

        return {
            "originProduct": {
                "statusType": "SALE",
                "leafCategoryId": settings.naver_default_leaf_category_id,
                "name": title[:100],
                "detailContent": settings.naver_default_detail_content_html,
                "images": images,
                "salePrice": int(sale_price_krw),
                "stockQuantity": 99,
                "detailAttribute": {
                    "afterServiceInfo": {
                        "afterServiceGuideContent": settings.naver_default_after_service_guide,
                        "afterServiceTelephoneNumber": settings.naver_default_after_service_tel,
                    },
                    "originAreaInfo": {
                        "originAreaCode": settings.naver_default_origin_area_code,
                        "importer": settings.naver_default_importer,
                    },
                    "productInfoProvidedNotice": {
                        "productInfoProvidedNoticeType": template_type,
                        notice_key: notice_block,
                    },
                },
            },
            "smartstoreChannelProduct": {
                "channelProductDisplayStatusType": "ON",
                "naverShoppingRegistration": {
                    "modelName": "상품 상세 참조",
                    "brand": "기타",
                    "manufacturerName": "기타",
                    "representativeKeyword": "기타",
                },
            },
        }

    def _notice_block_for_template(self, template_type: str) -> dict[str, str]:
        common = {
            "returnCostReason": "상품 상세 참조",
            "noRefundReason": "상품 상세 참조",
            "qualityAssuranceStandard": "관련 법 및 소비자 분쟁해결 기준 따름",
            "compensationProcedure": "상품 상세 참조",
            "troubleShootingContents": "상품 상세 참조",
        }
        if template_type == "DIGITAL_CONTENTS":
            return {
                **common,
                "productName": "상품 상세 참조",
                "modelName": "상품 상세 참조",
                "certificationInfo": "해당없음/상품 상세 참조",
                "manufacturer": "상품 상세 참조",
                "countryOfOrigin": "상품 상세 참조",
                "customerServiceNumber": "상품 상세 참조",
            }
        if template_type == "LIVING":
            return {
                **common,
                "item": "상품 상세 참조",
                "modelName": "상품 상세 참조",
                "certificationInfo": "해당없음/상품 상세 참조",
                "manufacturer": "상품 상세 참조",
                "countryOfOrigin": "상품 상세 참조",
                "customerServiceNumber": "상품 상세 참조",
            }
        return {
            **common,
            "item": "상품 상세 참조",
            "material": "상품 상세 참조",
            "color": "상품 상세 참조",
            "size": "상품 상세 참조",
            "manufacturer": "상품 상세 참조",
            "caution": "상품 상세 참조",
            "warrantyPolicy": "상품 상세 참조",
            "afterServiceDirector": "상품 상세 참조",
        }

    def _validate_required(self, payload: dict[str, Any], template_type: str) -> list[str]:
        required_paths = [
            "originProduct.statusType",
            "originProduct.leafCategoryId",
            "originProduct.name",
            "originProduct.detailContent",
            "originProduct.images",
            "originProduct.salePrice",
            "originProduct.stockQuantity",
            "originProduct.detailAttribute.afterServiceInfo.afterServiceGuideContent",
            "originProduct.detailAttribute.afterServiceInfo.afterServiceTelephoneNumber",
            "originProduct.detailAttribute.productInfoProvidedNotice.productInfoProvidedNoticeType",
            f"originProduct.detailAttribute.productInfoProvidedNotice.{NOTICE_KEYS[template_type]}",
            "smartstoreChannelProduct.channelProductDisplayStatusType",
            "smartstoreChannelProduct.naverShoppingRegistration",
        ]

        errors: list[str] = []
        for path in required_paths:
            value = self._get_path(payload, path)
            if value is None:
                errors.append(f"필수값 누락: {path}")
                continue
            if isinstance(value, str) and not value.strip():
                errors.append(f"필수값 비어있음: {path}")
            if isinstance(value, list) and len(value) == 0:
                errors.append(f"필수값 비어있음: {path}")

        rep_url = self._get_path(payload, "originProduct.images.0.url")
        if not rep_url:
            errors.append("필수값 누락: originProduct.images[0].url (대표이미지 URL)")
        return errors

    def _deep_merge(self, base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)
        for key, value in updates.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _get_path(self, payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, list):
                if not part.isdigit():
                    return None
                idx = int(part)
                if idx >= len(current):
                    return None
                current = current[idx]
            elif isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            else:
                return None
        return current
