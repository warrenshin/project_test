"use client";

import Link from "next/link";
import { use, useState } from "react";
import { getLesson, getQuiz, submitQuizAttempt, updateLessonProgress } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock } from "@/components/States";
import type { QuizAttemptResponse, QuizDetailResponse } from "@/lib/types";

const BLOCK_LABEL: Record<string, string> = {
  OBJECTIVE: "학습 목표",
  BODY: "본문",
  EXAMPLE: "예시",
  SUMMARY: "요약",
};

export default function LessonDetailPage({ params }: { params: Promise<{ lessonId: string }> }) {
  const { lessonId } = use(params);
  const lesson = useAsync(() => getLesson(lessonId), [lessonId]);

  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  const [xpAwarded, setXpAwarded] = useState<number | null>(null);

  const [quiz, setQuiz] = useState<QuizDetailResponse | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<QuizAttemptResponse | null>(null);

  async function handleComplete() {
    setCompleting(true);
    setCompleteError(null);
    try {
      const res = await updateLessonProgress(lessonId, "COMPLETED");
      setXpAwarded(res.xp_awarded);
      lesson.reload();
    } catch (err) {
      setCompleteError(err instanceof ApiError ? err.message : "완료 처리 중 오류가 발생했습니다.");
    } finally {
      setCompleting(false);
    }
  }

  async function handleStartQuiz(quizId: string) {
    setQuizLoading(true);
    setQuizError(null);
    setResult(null);
    setAnswers({});
    try {
      const data = await getQuiz(quizId);
      setQuiz(data);
    } catch (err) {
      setQuizError(err instanceof ApiError ? err.message : "퀴즈를 불러오지 못했습니다.");
    } finally {
      setQuizLoading(false);
    }
  }

  async function handleSubmitQuiz() {
    if (!quiz) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload: Record<string, string[]> = {};
      for (const q of quiz.questions) {
        payload[q.id] = answers[q.id] ? [answers[q.id]] : [];
      }
      const res = await submitQuizAttempt(quiz.id, payload);
      setResult(res);
      if (res.xp_awarded > 0) lesson.reload();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "퀴즈 제출 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  if (lesson.loading) return <LoadingBlock label="강의를 불러오는 중입니다..." />;
  if (lesson.error) return <ErrorBlock message={lesson.error} onRetry={lesson.reload} />;
  const data = lesson.data!;
  const allAnswered = quiz ? quiz.questions.every((q) => answers[q.id]) : false;

  return (
    <div className="stack">
      <Link href="/learn" className="link-back">
        ← 학습 목록
      </Link>
      <h1>{data.title}</h1>
      {data.learning_objective && <p className="muted">{data.learning_objective}</p>}
      <div className="row" style={{ flexWrap: "wrap" }}>
        <span className="badge badge-virtual">예상 {data.estimated_minutes}분</span>
        {data.progress?.status === "COMPLETED" && <span className="badge badge-virtual">완료함</span>}
      </div>

      {data.content_blocks.length === 0 ? (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>아직 등록된 본문이 없습니다.</p>
        </div>
      ) : (
        data.content_blocks
          .slice()
          .sort((a, b) => a.order_index - b.order_index)
          .map((block, idx) => (
            <div className="card" key={idx}>
              <h2>{BLOCK_LABEL[block.block_type] ?? block.block_type}</h2>
              <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{block.content}</p>
            </div>
          ))
      )}

      {data.source && (
        <p className="muted">출처: {data.source}{data.reviewed_by ? ` · 감수: ${data.reviewed_by}` : ""}</p>
      )}

      <div className="card">
        {data.progress?.status === "COMPLETED" ? (
          <p className="muted" style={{ margin: 0 }}>이미 완료한 강의입니다.</p>
        ) : (
          <button className="btn btn-primary btn-block" onClick={handleComplete} disabled={completing} type="button">
            {completing ? "처리 중..." : "학습 완료로 표시"}
          </button>
        )}
        {xpAwarded !== null && xpAwarded > 0 && (
          <p className="muted" style={{ marginTop: 8 }}>+{xpAwarded} XP 획득!</p>
        )}
        {completeError && <ErrorBlock message={completeError} />}
      </div>

      {data.quiz && (
        <div className="card stack">
          <h2>퀴즈: {data.quiz.title}</h2>
          <p className="muted">문항 {data.quiz.question_count}개 · 합격 기준 {Number(data.quiz.pass_score_pct)}%</p>

          {!quiz && (
            <button className="btn btn-block" onClick={() => handleStartQuiz(data.quiz!.id)} disabled={quizLoading} type="button">
              {quizLoading ? "불러오는 중..." : "퀴즈 풀기"}
            </button>
          )}
          {quizError && <ErrorBlock message={quizError} onRetry={() => handleStartQuiz(data.quiz!.id)} />}

          {quiz && !result && (
            <div className="stack">
              {quiz.questions.map((q, qi) => (
                <div key={q.id} className="stack">
                  <strong>{qi + 1}. {q.prompt}</strong>
                  <div className="stack">
                    {q.choices.map((c) => (
                      <label key={c.id} className="row" style={{ fontWeight: 400 }}>
                        <input
                          type="radio"
                          name={`q-${q.id}`}
                          checked={answers[q.id] === c.id}
                          onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: c.id }))}
                          style={{ width: "auto" }}
                        />
                        {c.label}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              <button className="btn btn-primary btn-block" onClick={handleSubmitQuiz} disabled={!allAnswered || submitting} type="button">
                {submitting ? "제출 중..." : "제출하기"}
              </button>
              {submitError && <ErrorBlock message={submitError} />}
            </div>
          )}

          {result && (
            <div className="stack">
              <div className={`banner ${result.passed ? "banner-info" : "banner-warning"}`}>
                점수 {Number(result.score_pct).toFixed(0)}% · {result.passed ? "합격" : "미합격"}
                {result.xp_awarded > 0 ? ` · +${result.xp_awarded} XP` : ""}
              </div>
              {quiz!.questions.map((q, qi) => {
                const r = result.results.find((x) => x.question_id === q.id);
                return (
                  <div className="card" key={q.id} style={{ marginBottom: 0 }}>
                    <p style={{ margin: 0, fontWeight: 600 }}>
                      {qi + 1}. {q.prompt} — {r?.correct ? "정답" : "오답"}
                    </p>
                    {r?.explanation && <p className="muted" style={{ margin: "4px 0 0" }}>{r.explanation}</p>}
                  </div>
                );
              })}
              {!result.passed && (
                <button className="btn btn-block" onClick={() => handleStartQuiz(data.quiz!.id)} type="button">
                  다시 풀기
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
