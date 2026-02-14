from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from typing import Optional
from urllib.parse import urljoin
from urllib.parse import quote
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

            web_pack = self._fetch_web_context_pack(title)

            llm_pack = self._llm_enrich(
                source_url=source_url,
                title=title,
                source_description=parsed.get('source_description', ''),
                key_features=parsed.get('key_features', []),
                specs=parsed.get('specs', {}),
                raw_text_snippet=parsed.get('raw_text_snippet', ''),
                web_context=web_pack.get('snippets', []),
                web_source_links=web_pack.get('links', []),
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
                'llm_product_judgement_ko': llm_pack.get('product_judgement_ko', ''),
                'llm_selling_points_ko': llm_pack.get('selling_points_ko', []),
                'llm_detail_outline_ko': llm_pack.get('detail_outline_ko', []),
                'llm_detail_sections_ko': llm_pack.get('detail_sections_ko', []),
                'source_links': web_pack.get('links', []),
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
                'llm_product_judgement_ko': '',
                'llm_selling_points_ko': [],
                'llm_detail_outline_ko': [],
                'llm_detail_sections_ko': [],
                'source_links': [],
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
        web_context: list[str],
        web_source_links: list[str],
    ) -> dict[str, Any]:
        if not settings.llm_enabled or not settings.openai_api_key:
            return self._heuristic_llm_pack(title, source_description, key_features)

        facts_blob = self._build_facts_blob(
            source_description=source_description,
            key_features=key_features,
            specs=specs,
            raw_text_snippet=raw_text_snippet,
        )

        prompt = {
            'source_url': source_url,
            'title': title,
            'source_description': source_description,
            'key_features': key_features[:20],
            'specs': specs,
            'raw_text_snippet': raw_text_snippet[:2500],
            'web_context': web_context[:12],
            'web_source_links': web_source_links[:10],
            'facts_blob': facts_blob[:4000],
            'task': {
                'goal': 'Korean open-market detail page materials with product judgement',
                'output_schema': {
                    'title_ko': 'string',
                    'product_judgement_ko': 'string',
                    'summary_ko': 'string',
                    'selling_points_ko': ['string'],
                    'detail_outline_ko': ['string'],
                    'detail_sections_ko': ['string'],
                    'translated_source_description_ko': 'string',
                    'translated_key_features_ko': ['string'],
                    'translated_specs_ko': {'key': 'value'},
                    'translated_raw_text_snippet_ko': 'string',
                },
                'constraints': [
                    'No medical/effect exaggeration',
                    'Do not invent unavailable specs',
                    'Korean concise and ecommerce-ready',
                    'Use web_context only as auxiliary evidence, prioritize extracted source text',
                    'Do NOT mention rating, review score, delivery quality, age recommendation unless explicitly present in facts_blob',
                    'If uncertain, omit the claim instead of guessing',
                    'Write in clean Korean for ecommerce detail page, avoid awkward literal translation',
                    'detail_sections_ko should be practical section-style copy for detail page blocks',
                    'When web_context suggests likely product identity or brand/IP story, include cautious judgement in product_judgement_ko',
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
            out = {
                'title_ko': str(parsed.get('title_ko') or title),
                'summary_ko': str(parsed.get('summary_ko') or ''),
                'selling_points_ko': self._to_str_list(parsed.get('selling_points_ko')),
                'detail_outline_ko': self._to_str_list(parsed.get('detail_outline_ko')),
                'detail_sections_ko': self._to_str_list(parsed.get('detail_sections_ko')),
                'product_judgement_ko': str(parsed.get('product_judgement_ko') or ''),
                'translated_source_description_ko': str(parsed.get('translated_source_description_ko') or ''),
                'translated_key_features_ko': self._to_str_list(parsed.get('translated_key_features_ko')),
                'translated_specs_ko': self._to_str_dict(parsed.get('translated_specs_ko')),
                'translated_raw_text_snippet_ko': str(parsed.get('translated_raw_text_snippet_ko') or ''),
            }
            return self._quality_postprocess(out, facts_blob)
        except Exception:
            return self._heuristic_llm_pack(title, source_description, key_features)

    def _heuristic_llm_pack(
        self, title: str, source_description: str, key_features: list[str]
    ) -> dict[str, Any]:
        return {
            'title_ko': title,
            'summary_ko': source_description[:300],
            'product_judgement_ko': '원문 기준으로 파악한 상품군입니다. 세부 사양은 원문/스펙을 우선 확인하세요.',
            'selling_points_ko': key_features[:5],
            'detail_outline_ko': [
                '상품 핵심 특징',
                '상세 스펙',
                '사용/관리 방법',
                '구매 전 확인사항',
            ],
            'detail_sections_ko': [
                '이 상품은 어떤 문제를 해결하는지',
                '핵심 장점과 차별점',
                '구매 전 체크해야 할 스펙',
                '추천 사용 시나리오',
                '주의사항 및 한계',
            ],
            'translated_source_description_ko': source_description[:600],
            'translated_key_features_ko': key_features[:20],
            'translated_specs_ko': {},
            'translated_raw_text_snippet_ko': '',
        }

    def _fetch_web_context_pack(self, query: str) -> dict[str, list[str]]:
        q = query.strip()
        if not q:
            return {"snippets": [], "links": []}
        snippets: list[str] = []
        links: list[str] = []
        queries = [q]
        queries.extend(self._extract_search_keywords(q))

        for qq in queries[:4]:
            s_html, l_html = self._fetch_ddg_html_search_context(qq)
            snippets.extend(s_html)
            links.extend(l_html)

        s1, l1 = self._fetch_duckduckgo_context(q)
        s2, l2 = self._fetch_wikipedia_context(q)
        snippets.extend(s1)
        snippets.extend(s2)
        links.extend(l1)
        links.extend(l2)
        return {
            "snippets": self._unique_keep_order([s for s in snippets if s])[:16],
            "links": self._unique_keep_order([x for x in links if x])[:12],
        }

    def _extract_search_keywords(self, title: str) -> list[str]:
        # 상품명에서 모델/브랜드 단서를 뽑아 보조 검색 쿼리를 만든다.
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\\-_/]{3,}", title)
        strong = [t for t in tokens if any(ch.isdigit() for ch in t) and len(t) >= 5]
        phrases = re.findall(r"[A-Za-z]{3,}\\s+[A-Za-z0-9\\-]{2,}", title)
        out = strong[:3] + phrases[:2]
        return self._unique_keep_order(out)

    def _fetch_ddg_html_search_context(self, query: str) -> tuple[list[str], list[str]]:
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                res = client.get("https://duckduckgo.com/html/", params={"q": query})
            if res.status_code >= 400:
                return [], []
            soup = BeautifulSoup(res.text or "", "html.parser")
            snippets: list[str] = []
            links: list[str] = []

            anchors = soup.select("a.result__a")
            if not anchors:
                anchors = soup.select("a[href]")
            for a in anchors[:5]:
                href = (a.get("href") or "").strip()
                title = a.get_text(" ", strip=True)
                if not href or not title:
                    continue
                if href.startswith("/"):
                    continue
                links.append(href)
                snippets.append(f"Search result: {title}")
                page_snippet = self._fetch_page_snippet(href)
                if page_snippet:
                    snippets.append(f"Page excerpt: {page_snippet}")
            return snippets, links
        except Exception:
            return [], []

    def _fetch_page_snippet(self, url: str) -> str:
        try:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                res = client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                        )
                    },
                )
            if res.status_code >= 400:
                return ""
            soup = BeautifulSoup(res.text or "", "html.parser")
            parts: list[str] = []
            h1 = soup.find("h1")
            if h1:
                parts.append(h1.get_text(" ", strip=True))
            for p in soup.find_all(["p", "li"]):
                t = p.get_text(" ", strip=True)
                if len(t) < 30:
                    continue
                parts.append(t)
                if len(" ".join(parts)) > 700:
                    break
            return " ".join(parts)[:800]
        except Exception:
            return ""

    def _fetch_duckduckgo_context(self, query: str) -> tuple[list[str], list[str]]:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    'https://api.duckduckgo.com/',
                    params={'q': query, 'format': 'json', 'no_html': '1', 'skip_disambig': '1'},
                )
            if res.status_code >= 400:
                return [], []
            data = res.json()
            out: list[str] = []
            links: list[str] = []
            abstract = str(data.get('AbstractText') or '').strip()
            if abstract:
                out.append(f"DDG: {abstract}")
            abstract_url = str(data.get('AbstractURL') or '').strip()
            if abstract_url:
                links.append(abstract_url)
            heading = str(data.get('Heading') or '').strip()
            if heading:
                out.append(f"DDG Heading: {heading}")
            for topic in data.get('RelatedTopics', [])[:6]:
                if isinstance(topic, dict):
                    txt = str(topic.get('Text') or '').strip()
                    if txt:
                        out.append(f"DDG Related: {txt}")
                    fu = str(topic.get('FirstURL') or '').strip()
                    if fu:
                        links.append(fu)
                    for sub in topic.get('Topics', [])[:3]:
                        st = str(sub.get('Text') or '').strip()
                        if st:
                            out.append(f"DDG Related: {st}")
                        sfu = str(sub.get('FirstURL') or '').strip()
                        if sfu:
                            links.append(sfu)
            return out, links
        except Exception:
            return [], []

    def _fetch_wikipedia_context(self, query: str) -> tuple[list[str], list[str]]:
        try:
            with httpx.Client(timeout=10.0) as client:
                search = client.get(
                    'https://ja.wikipedia.org/w/api.php',
                    params={
                        'action': 'query',
                        'list': 'search',
                        'srsearch': query,
                        'format': 'json',
                        'srlimit': 2,
                    },
                )
            if search.status_code >= 400:
                return [], []
            data = search.json()
            titles = [x.get('title') for x in data.get('query', {}).get('search', []) if x.get('title')]
            out: list[str] = []
            links: list[str] = []
            for t in titles:
                try:
                    with httpx.Client(timeout=10.0) as client:
                        s = client.get(
                            f'https://ja.wikipedia.org/api/rest_v1/page/summary/{quote(str(t))}'
                        )
                    if s.status_code >= 400:
                        continue
                    js = s.json()
                    ex = str(js.get('extract') or '').strip()
                    if ex:
                        out.append(f"Wikipedia({t}): {ex}")
                    cp = str(js.get('content_urls', {}).get('desktop', {}).get('page') or '').strip()
                    if cp:
                        links.append(cp)
                except Exception:
                    continue
            return out, links
        except Exception:
            return [], []

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

    def _build_facts_blob(
        self,
        *,
        source_description: str,
        key_features: list[str],
        specs: dict[str, str],
        raw_text_snippet: str,
    ) -> str:
        parts: list[str] = []
        if source_description:
            parts.append(f"[source_description] {source_description}")
        if key_features:
            parts.append("[key_features] " + " | ".join(key_features[:20]))
        if specs:
            kv = [f"{k}:{v}" for k, v in list(specs.items())[:30]]
            parts.append("[specs] " + " | ".join(kv))
        if raw_text_snippet:
            parts.append("[raw_text_snippet] " + raw_text_snippet[:2500])
        return "\n".join(parts)

    def _quality_postprocess(self, out: dict[str, Any], facts_blob: str) -> dict[str, Any]:
        text_fields = [
            "summary_ko",
            "product_judgement_ko",
            "translated_source_description_ko",
            "translated_raw_text_snippet_ko",
        ]
        for f in text_fields:
            out[f] = self._clean_text(str(out.get(f, "")))

        for f in ["selling_points_ko", "detail_outline_ko", "detail_sections_ko", "translated_key_features_ko"]:
            out[f] = [self._clean_text(x) for x in self._to_str_list(out.get(f))]
            out[f] = [x for x in out[f] if x]
        out["detail_sections_ko"] = [x for x in out.get("detail_sections_ko", []) if len(x) >= 18][:12]
        out["selling_points_ko"] = [x for x in out.get("selling_points_ko", []) if len(x) >= 6][:10]

        # 근거에 없는 평점/배송품질/연령문구 제거
        allow_rating = any(k in facts_blob.lower() for k in ["rating", "review", "별점", "평점"])
        if not allow_rating:
            block_words = ["평점", "별점", "배송", "만족도", "연령", "세 이상"]
            for f in text_fields:
                if any(w in out[f] for w in block_words):
                    out[f] = self._remove_sentences_with_words(out[f], block_words)
            for f in ["selling_points_ko", "detail_sections_ko", "translated_key_features_ko"]:
                out[f] = [x for x in out[f] if not any(w in x for w in block_words)]

        # 한글화 실패 시 원문 혼입 방지.
        for f in ["summary_ko", "product_judgement_ko", "translated_source_description_ko"]:
            if out.get(f) and not self._contains_korean(str(out.get(f))):
                out[f] = ""

        return out

    def _clean_text(self, s: str) -> str:
        t = s.replace("|", " ").replace("  ", " ").strip()
        t = re.sub(r"\s+\.", ".", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _remove_sentences_with_words(self, text: str, words: list[str]) -> str:
        chunks = re.split(r"(?<=[.!?])\s+", text)
        kept = [c for c in chunks if not any(w in c for w in words)]
        return " ".join(kept).strip()

    def _contains_korean(self, text: str) -> bool:
        return bool(re.search(r"[가-힣]", text or ""))

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
