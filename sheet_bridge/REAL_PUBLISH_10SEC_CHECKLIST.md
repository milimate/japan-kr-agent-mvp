# 실등록 전환 10초 점검표

실제로 네이버에 올리기 전에 아래 6개만 확인하세요.

## 1) 테스트 모드 해제 여부
- Render 환경변수: `NAVER_USE_REAL_API=true`

## 2) 네이버 인증값 입력 여부
- `NAVER_CLIENT_ID` 입력
- `NAVER_CLIENT_SECRET` 입력
- `NAVER_ACCOUNT_ID` 입력

## 3) 대표 이미지 기본값 확인
- `NAVER_DEFAULT_REPRESENTATIVE_IMAGE_URL`가 비어있지 않은지 확인

## 4) 시트 연결 주소 확인
- Apps Script `AGENT_BASE_URL`가 현재 Render URL과 같은지 확인

## 5) 소량 샘플만 실행
- 처음에는 링크 1개만 넣고 `선택 행 실행`으로 테스트

## 6) 결과 컬럼 확인
- `approval_status=approved`
- `publish_status=published`
- `market_product_id` 값이 비어있지 않음

---

## 문제 발생 시 즉시 롤백
1. Render 환경변수 `NAVER_USE_REAL_API=false`로 변경
2. 시트 실행 중단
3. 로그 확인 후 다시 테스트 모드에서 점검
