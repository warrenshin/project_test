# AI 시스템 프롬프트 버전 관리

명세서 7.7: 시스템 프롬프트와 정책은 버전 관리하며, 답변마다 모델·프롬프트 버전·
검색 문서 ID를 기록한다. 파일명은 `v{n}-{역할}.md` 형식을 사용한다 (예:
`v1-investment-coach.md`).

## 현재 상태

`v1-investment-coach.md`가 투자 코치 역할의 첫 버전이다. 실제 호출 코드는
`apps/api/app/domain/services/ai_coach.py`의 `SYSTEM_PROMPT` 상수에 이 파일과
동일한 내용을 유지한다 — 이 파일을 수정하면 `SYSTEM_PROMPT`도 함께 갱신해야
한다 (아직 런타임에 이 파일을 직접 읽어오지 않음, 배포 환경에 따라 content/
디렉터리가 없을 수 있어 상수로 이중화). 프롬프트를 바꿀 때는 파일명에 새 버전
번호를 붙이고(`v2-investment-coach.md`), `AI_COACH_PROMPT_VERSION` 환경변수와
함께 갱신한다.
