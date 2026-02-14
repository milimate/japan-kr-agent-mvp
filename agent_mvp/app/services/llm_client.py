from __future__ import annotations

import json
import re
from html import unescape
from typing import Optional
from urllib.parse import urlparse

import httpx


class LLMClient:
    """
    MVP 단계에서는 안전하게 deterministic 동작.
    다음 단계에서 실제 OpenAI 호출로 교체.
    """

    def detect_source_site(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        if 'amazon.co.jp' in host:
            return 'amazon_jp'
        if 'rakuten.co.jp' in host:
            return 'rakuten'
        if 'shopping.yahoo.co.jp' in host:
            return 'yahoo_jp'
        return 'other'

    def extract_product_from_link(self, source_url: str) -> dict:
        site = self.detect_source_site(source_url)
        try:
            html = self._fetch_html(source_url)
            extracted = self._extract_from_html(html)
            title = extracted.get("title") or self._fallback_title(site)
            price_jpy = extracted.get("price_jpy") or self._fallback_price(site)
            image_url = extracted.get("image_url")
            note = extracted.get("note", "HTML 추출")
            return {
                "source_site": site,
                "source_url": source_url,
                "title": title,
                "source_price_jpy": price_jpy,
                "representative_image_url": image_url,
                "note": note,
            }
        except Exception as e:
            return {
                "source_site": site,
                "source_url": source_url,
                "title": self._fallback_title(site),
                "source_price_jpy": self._fallback_price(site),
                "representative_image_url": None,
                "note": f"fallback extraction 사용: {str(e)[:100]}",
            }

    def _fetch_html(self, source_url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        }
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            res = client.get(source_url)
        if res.status_code >= 400:
            raise RuntimeError(f"HTTP {res.status_code}")
        return res.text or ""

    def _extract_from_html(self, html: str) -> dict:
        html = html or ""

        jsonld = self._extract_jsonld_product(html)
        if jsonld:
            return {
                "title": jsonld.get("name"),
                "price_jpy": self._to_int_price(jsonld.get("price")),
                "image_url": jsonld.get("image"),
                "note": "JSON-LD 추출",
            }

        og_title = self._find_meta(html, "og:title")
        og_image = self._find_meta(html, "og:image")
        meta_price = self._find_meta(html, "product:price:amount")
        title_tag = self._find_title_tag(html)
        title = og_title or title_tag
        return {
            "title": title,
            "price_jpy": self._to_int_price(meta_price),
            "image_url": og_image,
            "note": "meta/title 추출",
        }

    def _extract_jsonld_product(self, html: str) -> Optional[dict]:
        pattern = re.compile(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.IGNORECASE | re.DOTALL,
        )
        for m in pattern.finditer(html):
            raw = m.group(1).strip()
            if not raw:
                continue
            parsed = self._try_json_load(raw)
            if parsed is None:
                continue
            product = self._find_product_node(parsed)
            if not product:
                continue
            price = None
            offers = product.get("offers")
            if isinstance(offers, list) and offers:
                price = offers[0].get("price") or offers[0].get("lowPrice")
            elif isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
            image = product.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            return {"name": product.get("name"), "price": price, "image": image}
        return None

    def _find_product_node(self, obj):
        if isinstance(obj, list):
            for item in obj:
                found = self._find_product_node(item)
                if found:
                    return found
            return None
        if not isinstance(obj, dict):
            return None

        t = obj.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return obj
        if "@graph" in obj:
            return self._find_product_node(obj.get("@graph"))
        for _, v in obj.items():
            found = self._find_product_node(v)
            if found:
                return found
        return None

    def _find_meta(self, html: str, prop: str) -> Optional[str]:
        p = re.compile(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\'](.*?)["\']',
            re.IGNORECASE | re.DOTALL,
        )
        m = p.search(html)
        if not m:
            return None
        return unescape(m.group(1)).strip()

    def _find_title_tag(self, html: str) -> Optional[str]:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        return unescape(re.sub(r"\s+", " ", m.group(1))).strip()

    def _try_json_load(self, raw: str):
        try:
            return json.loads(raw)
        except Exception:
            try:
                fixed = raw.replace("\n", " ").replace("\t", " ")
                return json.loads(fixed)
            except Exception:
                return None

    def _to_int_price(self, value) -> Optional[int]:
        if value is None:
            return None
        text = re.sub(r"[^\d.]", "", str(value))
        if not text:
            return None
        try:
            return int(float(text))
        except Exception:
            return None

    def _fallback_title(self, site: str) -> str:
        fallback_titles = {
            "amazon_jp": "Amazon JP 샘플 상품",
            "rakuten": "Rakuten 샘플 상품",
            "yahoo_jp": "Yahoo JP 샘플 상품",
            "other": "JP Mall 샘플 상품",
        }
        return fallback_titles.get(site, "JP Mall 샘플 상품")

    def _fallback_price(self, site: str) -> int:
        return 6800 if site == "amazon_jp" else 4500
