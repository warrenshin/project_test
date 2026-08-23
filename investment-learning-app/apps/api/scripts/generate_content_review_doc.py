"""6~15강 콘텐츠 검수 문서(docs/content-review/lessons-06-15-review.md)를 시드
스크립트가 아니라 **실제 DB에 적용된 콘텐츠**에서 직접 추출해 생성한다.

이전 버전은 seed migration(c1a2b3d4e5f6)의 `_lessons()` 함수를 읽어 생성했지만,
이후 별도의 UPDATE-only 수정 migration(a9c8d7e6f5b4 등)이 내용을 고칠 때마다
이 함수를 함께 고쳐야 하는 이중 관리 문제가 있었다. 이제는 마이그레이션이 몇 개든,
DB에 실제로 반영된 최종 상태를 그대로 읽어 문서를 만든다 — 문서와 실제 서비스
콘텐츠가 어긋날 수 없다.

이 스크립트는 콘텐츠를 승인하지 않는다. source_confirmed_at이 NULL인 강의는
항상 "미확인"으로 표시한다.

    python -m scripts.generate_content_review_doc [--out PATH]
"""

import argparse
from pathlib import Path

from app.core.db import SessionLocal
from app.domain.learning import Choice, ContentBlock, Lesson, Question, Quiz

NEW_LESSON_CODES = [f"lesson-{n:02d}" for n in range(6, 16)]

BLOCK_ORDER = ["OBJECTIVE", "BODY", "EXAMPLE", "MISCONCEPTION", "SUMMARY", "SELF_CHECK", "TERMS", "PRACTICE", "SOURCE"]
BLOCK_LABEL = {
    "OBJECTIVE": "학습 목표", "BODY": "본문", "EXAMPLE": "예시", "MISCONCEPTION": "흔한 오해",
    "SUMMARY": "요약", "SELF_CHECK": "스스로 점검하기", "TERMS": "용어", "PRACTICE": "실습", "SOURCE": "출처 정보",
}

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs" / "content-review" / "lessons-06-15-review.md"


def _generate(db) -> str:
    lessons = (
        db.query(Lesson)
        .filter(Lesson.code.in_(NEW_LESSON_CODES))
        .order_by(Lesson.order_index)
        .all()
    )
    if len(lessons) != len(NEW_LESSON_CODES):
        found = sorted(l.code for l in lessons)
        raise RuntimeError(f"신규 강의 10개를 모두 찾지 못했습니다 — 찾은 code: {found}")

    out: list[str] = []
    out.append("# 6~15강 콘텐츠 검수 문서\n")
    out.append(
        "이 문서는 **실제 DB에 적용된 최종 콘텐츠**(seed + 이후 모든 수정 migration 반영 결과)에서 "
        "직접 추출해 생성했습니다. 수기 전사가 아니므로 이 문서와 실제 서비스 콘텐츠가 어긋날 수 "
        "없습니다. `python -m scripts.generate_content_review_doc`로 언제든 다시 생성할 수 있습니다.\n"
    )
    out.append(
        "## ⚠️ 검수 상태 — 반드시 읽어주세요\n\n"
        "- 이 10개 강의는 **에이전트(AI)가 작성**했습니다. 에이전트는 자기 자신이 작성한 콘텐츠를 "
        "**스스로 최종 승인(REVIEWED/PUBLISHED)하지 않습니다.**\n"
        "- 아래 각 강의의 '공식 출처 확인 여부'는 `source_confirmed_at` 컬럼이 NULL인 한 항상 "
        "**미확인**으로 표시됩니다. `source_url`이 채워져 있어도 그것은 검수자가 확인할 **후보**일 "
        "뿐, 원문이 실제로 대조 확인됐다는 뜻이 아닙니다.\n"
        "- 이 상태에서는 일반 사용자에게 **노출되지 않습니다** (공개 API는 `status=PUBLISHED`인 "
        "강의만 반환합니다).\n"
        "- 검수자가 아래 체크리스트를 확인하고, 필요 시 출처를 직접 대조한 뒤 "
        "`scripts/publish_lesson.py`로 강의별로 개별 승인해야 `PUBLISHED` 상태가 됩니다. "
        "일괄 승인 기능은 의도적으로 제공하지 않습니다.\n"
    )
    out.append("## 목차\n")
    for lesson in lessons:
        out.append(f"- [{lesson.code}: {lesson.title}](#{lesson.code})")
    out.append("")

    for lesson in lessons:
        out.append(f"---\n\n## {lesson.code}: {lesson.title} <a name=\"{lesson.code}\"></a>\n")
        out.append("### 승인 상태 체크리스트 (검수자가 작성)\n")
        out.append("- [ ] 본문 내용의 사실관계를 검수자가 직접 확인했다")
        out.append("- [ ] 퀴즈 문항·정답·해설이 본문과 일치하고 오류가 없다")
        out.append("- [ ] 아래 '공식 출처'가 있는 경우, 검수자가 원문을 직접 열어 대조했다")
        out.append("- [ ] 투자 추천·수익 보장 표현이 없다")
        out.append("- [ ] 변동성 정보(수수료/세율/환율/시장운영시간)가 '가정치'임이 본문에 명시되어 있다")
        source_confirmed = "예" if lesson.source_confirmed_at else "미확인(false)"
        out.append(
            f"- 현재 승인 상태: **{lesson.status} / {lesson.review_status}** "
            f"(공식 출처 직접 확인: {source_confirmed}, content_version={lesson.content_version})\n"
        )
        out.append(f"예상 소요 시간: {lesson.estimated_minutes}분  \n적용 시장 범위: `{lesson.market_scope}`\n")

        blocks = {b.block_type: b for b in db.query(ContentBlock).filter(ContentBlock.lesson_id == lesson.id).all()}
        for block_type in BLOCK_ORDER:
            block = blocks.get(block_type)
            if block is None:
                continue
            out.append(f"### {BLOCK_LABEL[block_type]}\n")
            out.append(f"{block.content}\n")

        out.append(f"- `source_url`: {lesson.source_url or '(없음)'}")
        out.append(f"- `source_confirmed_at`: {lesson.source_confirmed_at or 'NULL'}\n")

        quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson.id).first()
        out.append("### 퀴즈\n")
        if quiz is not None:
            questions = db.query(Question).filter(Question.quiz_id == quiz.id).order_by(Question.order_index).all()
            for qi, question in enumerate(questions, start=1):
                out.append(f"**Q{qi}. {question.prompt}**\n")
                choices = db.query(Choice).filter(Choice.question_id == question.id).order_by(Choice.order_index).all()
                for ci, choice in enumerate(choices, start=1):
                    mark = "✅ 정답" if choice.is_correct else "　　"
                    out.append(f"{ci}. [{mark}] {choice.label} — {choice.explanation or ''}")
                out.append(f"\n해설: {question.explanation}\n")
        out.append("")

    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="출력 파일 경로")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        content = _generate(db)
    finally:
        db.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    print(f"생성 완료: {out_path}")


if __name__ == "__main__":
    main()
