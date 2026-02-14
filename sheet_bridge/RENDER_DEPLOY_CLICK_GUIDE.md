# Render 배포 클릭 가이드 (초보자용)

## 목표
- 터미널 최소화
- Render에 서버 배포
- Google Sheets 버튼으로 자동화 실행

## A. GitHub에 코드 올리기 (한 번만)
1. GitHub 사이트에서 새 저장소를 만듭니다.
2. 현재 프로젝트 폴더(`/Users/taeheewoo/Documents/New project`)를 GitHub Desktop으로 열어 `Publish repository`를 누릅니다.
3. 업로드가 끝나면 GitHub 저장소 URL을 확인합니다.

## B. Render에서 배포 (클릭만)
1. [Render](https://render.com) 로그인
2. `New +` 클릭
3. `Blueprint` 클릭
4. 방금 만든 GitHub 저장소 선택
5. Render가 루트의 `render.yaml`을 읽어 서비스 설정을 자동으로 채웁니다.
6. `Apply` 클릭
7. 배포 완료까지 대기 (보통 수 분)
8. 서비스 URL 확인
   - 예: `https://japan-kr-agent-mvp.onrender.com`
9. 브라우저에서 아래 주소 열기
   - `https://서비스URL/health`
   - `{"status":"ok","env":"dev"}` 나오면 성공

## C. Google Sheets 연결
1. Google Sheets 열기
2. `확장 프로그램 -> Apps Script`
3. `sheet_bridge/apps_script_bridge.gs` 코드 붙여넣기
4. 코드 상단의 `AGENT_BASE_URL`를 Render URL로 변경
   - 예: `https://japan-kr-agent-mvp.onrender.com`
5. 저장 후 시트 새로고침
6. 상단 메뉴 `Agent 자동화` 확인
7. A열(`source_url`)에 링크 입력
8. `Agent 자동화 -> 선택 행 실행` 클릭

## D. 안전 테스트 모드 확인
Render 환경변수에서 아래가 `false`인지 확인
- `NAVER_USE_REAL_API=false`

이 상태면 네이버 실등록은 일어나지 않고 `mock`로만 테스트됩니다.

## E. LLM 사용 설정
Render 환경변수에서 아래 확인
- `LLM_ENABLED=true`
- `OPENAI_MODEL=gpt-4.1-mini`
- `OPENAI_API_KEY` 값 입력

설정 후 `Save, rebuild, and deploy` 실행

## F. 자주 막히는 문제
- `Agent API 오류 404`: `AGENT_BASE_URL` 오타/끝 슬래시 확인
- `Agent API 오류 500`: Render 로그에서 에러 메시지 확인
- 첫 호출이 느림: Render 무료 플랜은 슬립 후 첫 호출이 느릴 수 있음

## G. 실등록 전환 직전 체크
- `/Users/taeheewoo/Documents/New project/sheet_bridge/REAL_PUBLISH_10SEC_CHECKLIST.md`를 먼저 확인하세요.
