# Agent MVP (Link -> LLM 판단 -> 네이버 Tool 호출)

이 프로젝트는 링크 1개를 입력하면 아래를 순서대로 수행합니다.
1. 상품 정보 추출(제목/가격/이미지/특징/스펙/원문 텍스트)
2. 정책/리스크 판단
3. 가격/마진 계산
4. 승인 여부 결정
5. 승인 시 네이버 마켓 등록 API 호출(mock)

## 빠른 실행
1. Python 3.11+ 준비
2. 폴더 이동
```bash
cd /Users/taeheewoo/Documents/New\ project/agent_mvp
```
3. 가상환경/설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
4. 환경변수
```bash
cp .env.example .env
```
LLM 활성화:
```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
LLM_ENABLED=true
```
5. 서버 실행
```bash
uvicorn app.main:app --reload
```
6. 테스트 호출
```bash
curl -X POST http://127.0.0.1:8000/run-link \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://www.rakuten.co.jp/example-item"}'
```
`auto_publish`를 명시하면 요청 단위로 제어할 수 있습니다.
```bash
curl -X POST http://127.0.0.1:8000/run-link \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://www.rakuten.co.jp/example-item","auto_publish":true}'
```

## 네이버 실연동 켜기
1. `.env`에서 아래를 설정
```bash
NAVER_USE_REAL_API=true
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
NAVER_ACCOUNT_ID=...
NAVER_DEFAULT_REPRESENTATIVE_IMAGE_URL=https://...
```
2. 서버 재시작
3. payload 사전 생성/검증
```bash
curl -X POST http://127.0.0.1:8000/naver/build-payload \
  -H "Content-Type: application/json" \
  -d '{"title":"테스트 상품","sale_price_krw":19900,"template_hint":"FASHION_ITEMS","overrides":{}}'
```
4. 응답의 `validation_errors`가 비어있는지 확인
5. 원시 payload 등록 테스트
```bash
curl -X POST http://127.0.0.1:8000/naver/publish-raw \
  -H "Content-Type: application/json" \
  -d '{"product_payload":{"originProduct":{"statusType":"SALE","leafCategoryId":50000000,"name":"테스트 상품","salePrice":19900,"stockQuantity":99,"detailContent":"<p>테스트</p>"}}}'
```

## 현재 상태
- 네이버 전용 구조로 고정
- `NAVER_USE_REAL_API=false`면 mock 동작
- `NAVER_USE_REAL_API=true`면 인증 토큰 발급 후 네이버 상품등록 API 호출
- `run-link`는 링크 HTML에서 제목/가격/이미지/특징/스펙/원문발췌 자동 추출
- LLM 활성화 시 한국어 요약/셀링포인트/상세구성 자동 생성(`llm_summary_ko`, `llm_selling_points_ko`, `llm_detail_outline_ko`)
- `run-link-batch`는 링크 여러 개를 한 번에 처리 (시트 연동용)
- `POST /naver/build-payload`에서 기본 payload 생성 + 필수값 누락 검증 가능
- `template_hint`를 안 넣으면 제목 기반으로 템플릿 자동선택(`FASHION_ITEMS`, `LIVING`, `DIGITAL_CONTENTS`)
- 실서비스 등록 성공을 위해서는 카테고리/고시정보/배송/옵션 등 필수필드를 `overrides`로 확장해야 합니다.

## Google Sheets 통합
- 시트 중심으로 쓰려면 `/Users/taeheewoo/Documents/New project/sheet_bridge`를 사용
- Apps Script에서 메뉴 버튼(`선택 행 실행`, `전체 행 실행`)으로 API 호출 가능
- 시트 연동 상세는 `/Users/taeheewoo/Documents/New project/sheet_bridge/README.md` 참고

## 폴더 구조
- `app/main.py`: API 엔드포인트
- `app/services/pipeline.py`: 링크 처리 파이프라인
- `app/services/naver_client.py`: 네이버 OAuth/상품등록 HTTP 클라이언트
- `app/services/naver_payload_builder.py`: 네이버 payload 생성/필수값 검증
- `app/services/llm_client.py`: LLM 판단 래퍼(현재 heuristic + 확장 포인트)
- `app/policies.py`: 금지/주의 정책 룰
- `app/tools/naver_market.py`: 네이버 마켓 API(mock/real) 어댑터
