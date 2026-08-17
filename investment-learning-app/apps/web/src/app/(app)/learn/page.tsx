"use client";

import Link from "next/link";
import { getLearningPaths } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";

export default function LearnPage() {
  const paths = useAsync(() => getLearningPaths(), []);

  return (
    <div className="stack">
      <h1>학습</h1>

      {paths.loading && <LoadingBlock label="학습 과정을 불러오는 중입니다..." />}
      {paths.error && <ErrorBlock message={paths.error} onRetry={paths.reload} />}
      {paths.data && paths.data.length === 0 && (
        <EmptyBlock message="아직 공개된 학습 과정이 없습니다." />
      )}

      {paths.data?.map((path) => (
        <div key={path.id} className="stack">
          <div className="card">
            <h2>{path.title}</h2>
            {path.description && <p className="muted">{path.description}</p>}
          </div>
          {path.courses.map((course) => (
            <div key={course.id} className="card">
              <h2>{course.title}</h2>
              <div className="stack">
                {course.modules.flatMap((mod) => mod.lessons).length === 0 && (
                  <EmptyBlock message="이 과정에는 아직 강의가 없습니다." />
                )}
                {course.modules.map((mod) => (
                  <div key={mod.id} className="stack">
                    {mod.lessons.map((lesson) => (
                      <Link
                        key={lesson.id}
                        href={`/learn/${lesson.id}`}
                        className="row-between card"
                        style={{ marginBottom: 0, textDecoration: "none" }}
                      >
                        <span>{lesson.title}</span>
                        <span className="muted">{lesson.estimated_minutes}분</span>
                      </Link>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
