# 강의 콘텐츠

명세서 부록 B "첫 30개 강의 권장 목차" 기준으로 마이크로 강의를 작성한다.
콘텐츠 계층(6.2): `LearningPath > Course > Module > Lesson > (ContentBlock, Quiz, PracticeMission)`

각 강의 파일에는 다음을 포함한다.

- 학습목표, 본문, 예시, 핵심요약
- 이해 확인 퀴즈 (`content/quizzes/`에 연결)
- 출처와 최종 검수일 (콘텐츠 노후화 방지, 20장 위험 대응)

## 현재 상태

1~5강("투자는 무엇인가" ~ "채권과 금리")이 DB 시드 마이그레이션
(`apps/api/alembic/versions/..._seed_first_5_lessons_with_quizzes.py`)으로
작성되어 실제 API(`GET /v1/learning/paths`, `GET /v1/lessons/{id}`)로 서빙된다.
각 강의는 학습목표·본문·예시·핵심요약 4개 콘텐츠 블록과 2문항 이해 확인 퀴즈로
구성했다. 나머지 6~30강(부록 B)은 아직 작성되지 않았다 — 콘텐츠는 마이그레이션이
아니라 관리자 웹(CMS, 11.1)에서 작성·검수·게시하는 것이 정상 경로이므로, 이 5개는
"콘텐츠 없이도 학습 엔진이 동작함을 보여주는 시드"로 이해하고 후속 강의는 CMS
구현과 함께 채워나간다.
