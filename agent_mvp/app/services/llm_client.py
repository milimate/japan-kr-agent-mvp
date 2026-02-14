from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from typing import Optional
from urllib.parse import urljoin
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings


class LLMClient:
    def detect_source_site(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        if 'amazon.co.jp' in host:
            return 'amazon_jp'
        if 'rakuten.co.jp' in host:
            return 'rakuten'
        if 'shopping.yahoo.co.jp' in host:
            return 'yahoo_jp'
        return 'other'

    def extract_product_from_link(self, source_url: str) -> dict[str, Any]:
        site = self.detect_source_site(source_url)
        try:
            html = self._fetch_html(source_url)
            parsed = self._extract_from_html(source_url, html)

            title = parsed.get('title') or self._fallback_title(site)
            source_price_jpy = parsed.get('price_jpy') or self._fallback_price(site)
            images = parsed.get('image_urls') or []
            representative_image_url = parsed.get('representative_image_url')
            if not representative_image_url and images:
                representative_image_url = images[0]

            llm_pack = self._llm_enrich(
                source_url=source_url,
                title=title,
                source_description=parsed.get('source_description', ''),
                key_features=parsed.get('key_features', []),
                specs=parsed.get('specs', {}),
                raw_text_snippet=parsed.get('raw_text_snippet', ''),
            )

            return {
                'source_site': site,
                'source_url': source_url,
                'title': llm_pack.get('title_ko') or title,
                'source_price_jpy': source_price_jpy,
                'representative_image_url': representative_image_url,
                'image_urls': images,
                'source_description': llm_pack.get('translated_source_description_ko')
                or parsed.get('source_description', ''),
                'key_features': llm_pack.get('translated_key_features_ko') or parsed.get('key_features', []),
                'specs': llm_pack.get('translated_specs_ko') or parsed.get('specs', {}),
                'raw_text_snippet': llm_pack.get('translated_raw_text_snippet_ko')
                or parsed.get('raw_text_snippet', ''),
                'llm_summary_ko': llm_pack.get('summary_ko', ''),
                'llm_selling_points_ko': llm_pack.get('selling_points_ko', []),
                'llm_detail_outline_ko': llm_pack.get('detail_outline_ko', []),
                'note': parsed.get('note', 'HTML 추출'),
            }
        except Exception as e:
            return {
                'source_site': site,
                'source_url': source_url,
                'title': self._fallback_title(site),
                'source_price_jpy': self._fallback_price(site),
                'representative_image_url': None,
                'image_urls': [],
                'source_description': '',
                'key_features': [],
                'specs': {},
                'raw_text_snippet': '',
                'llm_summary_ko': '',
                'llm_selling_points_ko': [],
                'llm_detail_outline_ko': [],
                'note': f'fallback extraction 사용: {str(e)[:100]}',
            }

    def _fetch_html(self, source_url: str) -> str:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'
            )
        }
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            res = client.get(source_url)
        if res.status_code >= 400:
            raise RuntimeError(f'HTTP {res.status_code}')
        return res.text or ''

    def _extract_from_html(self, source_url: str, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html or '', 'html.parser')

        jsonld = self._extract_jsonld_product(html)
        meta_title = self._find_meta(html, 'og:title')
        title_tag = self._find_title_tag(html)
        meta_desc = self._find_meta(html, 'og:description') or self._find_meta(html, 'description') or ''
        meta_price = self._find_meta(html, 'product:price:amount')

        title = None
        price_jpy = None
        jsonld_images: list[str] = []
        if jsonld:
            title = jsonld.get('name')
            price_jpy = self._to_int_price(jsonld.get('price'))
            raw_images = jsonld.get('images') or []
            jsonld_images = [self._abs_url(source_url, u) for u in raw_images if u]

        if not title:
            h1 = soup.find('h1')
            title = (h1.get_text(' ', strip=True) if h1 else None) or meta_title or title_tag
        if not price_jpy:
            price_jpy = self._to_int_price(meta_price)

        og_image = self._find_meta(html, 'og:image')
        all_images = []
        if og_image:
            all_images.append(self._abs_url(source_url, og_image))
        all_images.extend(jsonld_images)
        all_images.extend(self._extract_img_urls(source_url, soup))
        all_images = self._unique_keep_order([u for u in all_images if u])[:15]

        key_features = self._extract_features(soup)
        specs = self._extract_specs(soup)
        raw_text_snippet = self._extract_text_snippet(soup)

        note = 'JSON-LD 추출' if jsonld else 'meta/title 추출'
        return {
            'title': title,
            'price_jpy': price_jpy,
            'representative_image_url': all_images[0] if all_images else None,
            'image_urls': all_images,
            'source_description': meta_desc,
            'key_features': key_features,
            'specs': specs,
            'raw_text_snippet': raw_text_snippet,
            'note': note,
        }

    def _extract_img_urls(self, source_url: str, soup: BeautifulSoup) -> list[str]:
        urls: list[str] = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if not src:
                continue
            src = src.strip()
            if not src or src.startswith('data:image'):
                continue
            urls.append(self._abs_url(source_url, src))
        return urls

    def _extract_features(self, soup: BeautifulSoup) -> list[str]:
        features: list[str] = []
        for li in soup.find_all('li'):
            t = li.get_text(' ', strip=True)
            if len(t) < 8 or len(t) > 160:
                continue
            if re.search(r'^(home|login|cart|menu)$', t, re.IGNORECASE):
                continue
            features.append(t)
            if len(features) >= 20:
                break
        return self._unique_keep_order(features)

    def _extract_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        specs: dict[str, str] = {}

        # table 기반 스펙
        for tr in soup.find_all('tr'):
            th = tr.find('th')
            td = tr.find('td')
            if not th or not td:
                continue
            k = th.get_text(' ', strip=True)
            v = td.get_text(' ', strip=True)
            if not k or not v:
                continue
            if len(k) > 80 or len(v) > 300:
                continue
            specs[k] = v
            if len(specs) >= 20:
                break

        # dl 기반 스펙
        if len(specs) < 20:
            dts = soup.find_all('dt')
            for dt in dts:
                dd = dt.find_next_sibling('dd')
                if not dd:
                    continue
                k = dt.get_text(' ', strip=True)
                v = dd.get_text(' ', strip=True)
                if not k or not v:
                    continue
                if len(k) > 80 or len(v) > 300:
                    continue
                if k not in specs:
                    specs[k] = v
                if len(specs) >= 20:
                    break

        return specs

    def _extract_text_snippet(self, soup: BeautifulSoup) -> str:
        blocks: list[str] = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'p']):
            t = tag.get_text(' ', strip=True)
            if len(t) < 15:
                continue
            blocks.append(t)
            if len(' '.join(blocks)) > 3500:
                break
        snippet = '\n'.join(blocks)
        return snippet[:4000]

    def _llm_enrich(
        self,
        *,
        source_url: str,
        title: str,
        source_description: str,
        key_features: list[str],
        specs: dict[str, str],
        raw_text_snippet: str,
    ) -> dict[str, Any]:
        if not settings.llm_enabled or not settings.openai_api_key:
            return self._heuristic_llm_pack(title, source_description, key_features)

        prompt = {
            'source_url': source_url,
            'title': title,
            'source_description': source_description,
            'key_features': key_features[:20],
            'specs': specs,
            'raw_text_snippet': raw_text_snippet[:2500],
                'task': {
                    'goal': 'Korean open-market detail page materials',
                    'output_schema': {
                        'title_ko': 'string',
                        'summary_ko': 'string',
                        'selling_points_ko': ['string'],
                        'detail_outline_ko': ['string'],
                        'translated_source_description_ko': 'string',
                        'translated_key_features_ko': ['string'],
                        'translated_specs_ko': {'key': 'value'},
                        'translated_raw_text_snippet_ko': 'string',
                    },
                    'constraints': [
                        'No medical/effect exaggeration',
                        'Do not invent unavailable specs',
                        'Korean concise and ecommerce-ready',
                ],
            },
        }

        headers = {
            'Authorization': f'Bearer {settings.openai_api_key}',
            'Content-Type': 'application/json',
        }
        body = {
            'model': settings.openai_model,
            'temperature': 0.2,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You are an ecommerce copy assistant. Return ONLY valid JSON. '
                        'Use factual input only, no hallucination.'
                    ),
                },
                {'role': 'user', 'content': json.dumps(prompt, ensure_ascii=False)},
            ],
        }

        try:
            with httpx.Client(timeout=35.0) as client:
                res = client.post('https://api.openai.com/v1/chat/completions', headers=headers, json=body)
            if res.status_code >= 400:
                return self._heuristic_llm_pack(title, source_description, key_features)
            payload = res.json()
            content = payload['choices'][0]['message']['content']
            parsed = self._extract_json_object(content)
            if not parsed:
                return self._heuristic_llm_pack(title, source_description, key_features)
            return {
                'title_ko': str(parsed.get('title_ko') or title),
                'summary_ko': str(parsed.get('summary_ko') or ''),
                'selling_points_ko': self._to_str_list(parsed.get('selling_points_ko')),
                'detail_outline_ko': self._to_str_list(parsed.get('detail_outline_ko')),
                'translated_source_description_ko': str(parsed.get('translated_source_description_ko') or ''),
                'translated_key_features_ko': self._to_str_list(parsed.get('translated_key_features_ko')),
                'translated_specs_ko': self._to_str_dict(parsed.get('translated_specs_ko')),
                'translated_raw_text_snippet_ko': str(parsed.get('translated_raw_text_snippet_ko') or ''),
            }
        except Exception:
            return self._heuristic_llm_pack(title, source_description, key_features)

    def _heuristic_llm_pack(
        self, title: str, source_description: str, key_features: list[str]
    ) -> dict[str, Any]:
        return {
            'title_ko': title,
            'summary_ko': source_description[:300],
            'selling_points_ko': key_features[:5],
            'detail_outline_ko': [
                '상품 핵심 특징',
                '상세 스펙',
                '사용/관리 방법',
                '구매 전 확인사항',
            ],
            'translated_source_description_ko': source_description[:600],
            'translated_key_features_ko': key_features[:20],
            'translated_specs_ko': {},
            'translated_raw_text_snippet_ko': '',
        }

    def _extract_json_object(self, text: str) -> Optional[dict[str, Any]]:
        text = text.strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def _to_str_list(self, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
        return out

    def _to_str_dict(self, v: Any) -> dict[str, str]:
        if not isinstance(v, dict):
            return {}
        out: dict[str, str] = {}
        for k, val in v.items():
            ks = str(k).strip()
            vs = str(val).strip()
            if ks and vs:
                out[ks] = vs
        return out

    def _extract_jsonld_product(self, html: str) -> Optional[dict[str, Any]]:
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
            offers = product.get('offers')
            if isinstance(offers, list) and offers:
                price = offers[0].get('price') or offers[0].get('lowPrice')
            elif isinstance(offers, dict):
                price = offers.get('price') or offers.get('lowPrice')
            images = product.get('image')
            if isinstance(images, str):
                images = [images]
            if not isinstance(images, list):
                images = []
            return {'name': product.get('name'), 'price': price, 'images': images}
        return None

    def _find_product_node(self, obj: Any) -> Optional[dict[str, Any]]:
        if isinstance(obj, list):
            for item in obj:
                found = self._find_product_node(item)
                if found:
                    return found
            return None
        if not isinstance(obj, dict):
            return None

        t = obj.get('@type')
        if t == 'Product' or (isinstance(t, list) and 'Product' in t):
            return obj
        if '@graph' in obj:
            return self._find_product_node(obj.get('@graph'))
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
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        return unescape(re.sub(r'\s+', ' ', m.group(1))).strip()

    def _try_json_load(self, raw: str) -> Optional[Any]:
        try:
            return json.loads(raw)
        except Exception:
            try:
                fixed = raw.replace('\n', ' ').replace('\t', ' ')
                return json.loads(fixed)
            except Exception:
                return None

    def _to_int_price(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        text = re.sub(r'[^\d.]', '', str(value))
        if not text:
            return None
        try:
            return int(float(text))
        except Exception:
            return None

    def _abs_url(self, source_url: str, u: str) -> str:
        return urljoin(source_url, u.strip())

    def _unique_keep_order(self, arr: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in arr:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    def _fallback_title(self, site: str) -> str:
        fallback_titles = {
            'amazon_jp': 'Amazon JP 샘플 상품',
            'rakuten': 'Rakuten 샘플 상품',
            'yahoo_jp': 'Yahoo JP 샘플 상품',
            'other': 'JP Mall 샘플 상품',
        }
        return fallback_titles.get(site, 'JP Mall 샘플 상품')

    def _fallback_price(self, site: str) -> int:
        return 6800 if site == 'amazon_jp' else 4500
