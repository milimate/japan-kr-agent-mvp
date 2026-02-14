# Google Sheets + Agent 통합 사용법 (터미널 최소화)

이 방식은 시트에서 버튼만 눌러 자동화를 실행합니다.

## 1) 시트 준비
1. Google Sheets 새 문서 생성
2. 시트 이름을 `products`로 변경
3. `sheet_template.csv` 내용을 붙여넣기

## 2) Apps Script 붙여넣기
1. 시트 상단 `확장 프로그램 -> Apps Script`
2. `Code.gs` 전체 삭제
3. `apps_script_bridge.gs` 전체 붙여넣기
4. 저장

## 3) URL 설정 (중요)
`CONFIG.AGENT_BASE_URL`를 배포된 에이전트 주소로 변경
- 예: `https://my-agent.onrender.com`

## 4) 메뉴 실행
1. 시트로 돌아가 새로고침
2. 상단 메뉴에 `Agent 자동화` 생성 확인
3. `헤더 만들기` 1회 실행 (필요시)
4. B열이 아니라 A열 `source_url`에 링크 입력
5. `Agent 자동화 -> 선택 행 실행` 또는 `전체 행 실행`

## 5) 결과 확인
자동으로 아래 컬럼이 채워집니다.
- 제목/원가/목표가/마진/승인상태/발행상태/메시지

## 6) 안전 테스트 모드
에이전트 서버 `.env`에서 아래 유지:
- `NAVER_USE_REAL_API=false`
그러면 네이버 실제 등록 없이 mock 결과만 기록됩니다.
