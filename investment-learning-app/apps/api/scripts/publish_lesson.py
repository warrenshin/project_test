"""강의 하나를 REVIEW_REQUIRED -> REVIEWED/PUBLISHED로 승인하는 운영자 전용 CLI.

*** 이 스크립트는 사람 운영자가 터미널에서 직접 실행해야 한다. ***
에이전트(자동화)가 스스로 작성한 콘텐츠를 이 스크립트로 스스로 승인해서는
안 된다 — 그것이 이 스크립트가 존재하는 이유 자체(작성과 승인의 분리)를
무너뜨린다. HTTP API가 아니라 CLI로 만든 이유: 이 저장소에는 아직 "진짜
관리자"를 구분할 인증 구조(역할·권한 체계)가 없다 — 온라인 API로 노출하면
어떤 로그인 사용자든 호출할 수 있게 될 위험이 있어, 서버 콘솔/배포 파이프라인
접근 권한이 있는 사람만 실행 가능한 CLI를 우선한다.

사용 예:

    python -m scripts.publish_lesson \\
        --code lesson-07 \\
        --content-version v1 \\
        --reviewer "hong.gildong" \\
        --source-verified false \\
        --note "주문 방식 개념 설명 검수 완료. 출처 URL 없음(일반 개념 설명)."

    python -m scripts.publish_lesson \\
        --code lesson-06 \\
        --content-version v1 \\
        --reviewer "hong.gildong" \\
        --source-verified true \\
        --note "한국거래소 open.krx.co.kr, NYSE/Nasdaq 공식 페이지에서 정규장 시간을 직접 확인함."

안전장치(전부 거절 사유가 있으면 비정상 종료 코드로 끝나고 아무것도 바꾸지 않음):
- 존재하지 않는 code -> 거절
- lesson.status가 READY_FOR_REVIEW가 아님(단, 이미 이 요청과 동일한 내용으로
  PUBLISHED된 상태라면 멱등하게 성공 처리) -> 거절
- --content-version이 현재 lesson.content_version과 다름(그 사이 콘텐츠가
  바뀌었다는 뜻) -> 거절
- lesson.source_url이 있는데 --source-verified true가 아님 -> 거절
- lesson.source_url이 없는데 --source-verified true임(확인할 대상 자체가 없는데
  "확인했다"는 감사기록을 남기는 의미상 모순) -> 거절
- 한 번에 하나의 code만 승인한다(여러 강의 일괄 처리 옵션 없음)
- 승인마다 lesson_review_audits에 감사기록을 남긴다((lesson_id,
  content_version, action) unique 제약 + SAVEPOINT로 동일 요청 재실행이
  멱등하다 — 이 저장소 전체에서 쓰는 동시성 안전 패턴과 동일)
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.db import SessionLocal
from app.domain.learning import (
    CONTENT_PUBLISHED,
    CONTENT_READY_FOR_REVIEW,
    REVIEW_REVIEWED,
    Lesson,
    LessonReviewAudit,
)

ACTION_PUBLISH = "PUBLISHED"


class PublishRejected(Exception):
    """승인 요청이 안전장치에 걸려 거절됐다 — 아무것도 바뀌지 않았다."""


@dataclass
class PublishResult:
    already_done: bool
    lesson_id: str
    code: str
    content_version: str


def publish_lesson(
    db: DbSession,
    *,
    code: str,
    expected_content_version: str,
    reviewer: str,
    reviewed_at: datetime,
    source_verified: bool,
    note: str,
) -> PublishResult:
    if not reviewer.strip():
        raise PublishRejected("reviewer는 비어 있을 수 없습니다.")
    if not note.strip():
        raise PublishRejected("승인 사유(note)는 비어 있을 수 없습니다 — 왜 승인하는지 기록이 남아야 합니다.")

    lesson = db.query(Lesson).filter(Lesson.code == code).first()
    if lesson is None:
        raise PublishRejected(f"잘못된 lesson code입니다: {code!r} — 존재하지 않습니다.")

    if lesson.content_version != expected_content_version:
        raise PublishRejected(
            f"content_version 불일치: 승인 요청은 {expected_content_version!r}를 예상했지만 "
            f"현재 콘텐츠는 {lesson.content_version!r}입니다 — 그 사이 콘텐츠가 바뀌었을 수 있으니 "
            "다시 검수해주세요."
        )

    # 멱등 경로: 이미 이 콘텐츠 버전으로 PUBLISHED + 감사기록이 있다면 그대로 성공 처리한다
    # (같은 승인 요청을 실수로 두 번 실행해도 안전).
    if lesson.status == CONTENT_PUBLISHED and lesson.review_status == REVIEW_REVIEWED:
        existing_audit = (
            db.query(LessonReviewAudit)
            .filter(
                LessonReviewAudit.lesson_id == lesson.id,
                LessonReviewAudit.content_version == expected_content_version,
                LessonReviewAudit.action == ACTION_PUBLISH,
            )
            .first()
        )
        if existing_audit is not None:
            return PublishResult(
                already_done=True, lesson_id=str(lesson.id), code=lesson.code, content_version=lesson.content_version
            )
        raise PublishRejected(
            f"lesson {code!r}는 이미 PUBLISHED 상태이지만 이 요청에 대한 감사기록이 없습니다 — "
            "다른 경로로 상태가 바뀐 것으로 보입니다. 수동으로 확인해주세요."
        )

    if lesson.status != CONTENT_READY_FOR_REVIEW:
        raise PublishRejected(
            f"lesson {code!r}의 현재 status는 {lesson.status!r}입니다 — "
            f"{CONTENT_READY_FOR_REVIEW!r} 상태에서만 승인할 수 있습니다."
        )

    if lesson.source_url and not source_verified:
        raise PublishRejected(
            f"lesson {code!r}에는 확인이 필요한 출처 URL({lesson.source_url})이 있습니다 — "
            "--source-verified true로 원문을 직접 확인했음을 명시해야 승인할 수 있습니다. "
            "검색 결과나 제3자 요약만으로는 확인 완료로 인정되지 않습니다."
        )

    if source_verified and not lesson.source_url:
        raise PublishRejected(
            f"lesson {code!r}에는 연결된 출처 URL이 없습니다 — 확인할 대상이 없는데 "
            "--source-verified true를 지정하는 것은 의미가 없습니다(감사기록에 '출처를 "
            "확인했다'는 거짓 기록이 남습니다). 출처 URL이 없는 강의는 --source-verified "
            "false로 승인하세요(이 경우 사람이 본문·퀴즈 내용 자체는 검토했지만, 별도로 "
            "대조할 외부 공식 출처가 애초에 없었다는 뜻입니다)."
        )

    lesson.review_status = REVIEW_REVIEWED
    lesson.reviewed_by = reviewer
    lesson.reviewed_at = reviewed_at.date()
    if lesson.source_url and source_verified:
        lesson.source_confirmed_at = reviewed_at.date()
    lesson.status = CONTENT_PUBLISHED

    audit = LessonReviewAudit(
        lesson_id=lesson.id, lesson_code=lesson.code, content_version=expected_content_version,
        action=ACTION_PUBLISH, reviewer=reviewer, reviewed_at=reviewed_at, source_verified=source_verified,
        note=note, performed_at=datetime.now(timezone.utc),
    )
    db.add(audit)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.rollback()
        # 동시에 같은 요청이 두 번 들어온 경우(레이스) — 멱등하게 성공 처리한다.
        return PublishResult(
            already_done=True, lesson_id=str(lesson.id), code=lesson.code, content_version=lesson.content_version
        )

    db.commit()
    return PublishResult(
        already_done=False, lesson_id=str(lesson.id), code=lesson.code, content_version=lesson.content_version
    )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"true/false로 입력해주세요: {value!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code", required=True, help="승인할 강의의 lesson code (예: lesson-07). 한 번에 하나만.")
    parser.add_argument("--content-version", required=True, dest="content_version", help="승인 대상으로 확인한 content_version")
    parser.add_argument("--reviewer", required=True, help="검수자 식별자(실명 또는 사번 등)")
    parser.add_argument(
        "--reviewed-at", dest="reviewed_at", default=None,
        help="검수 시각(ISO 8601, 예: 2026-08-23T10:00:00+00:00). 생략하면 지금 시각을 쓴다.",
    )
    parser.add_argument(
        "--source-verified", required=True, dest="source_verified", type=_parse_bool,
        help="공식 출처 원문을 직접 확인했으면 true, 아니면 false (검색 결과·요약본만으로는 true로 표시하지 말 것)",
    )
    parser.add_argument("--note", required=True, help="승인 사유 또는 검수 메모(필수)")
    args = parser.parse_args()

    reviewed_at = datetime.fromisoformat(args.reviewed_at) if args.reviewed_at else datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        result = publish_lesson(
            db, code=args.code, expected_content_version=args.content_version, reviewer=args.reviewer,
            reviewed_at=reviewed_at, source_verified=args.source_verified, note=args.note,
        )
    except PublishRejected as exc:
        print(f"거절됨: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

    if result.already_done:
        print(f"이미 승인·게시되어 있습니다(멱등): {result.code} (content_version={result.content_version})")
    else:
        print(f"승인·게시 완료: {result.code} (content_version={result.content_version}, lesson_id={result.lesson_id})")


if __name__ == "__main__":
    main()
