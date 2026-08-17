"use client";

import Link from "next/link";
import { listMyJournals } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";

export default function JournalListPage() {
  const journals = useAsync(() => listMyJournals(), []);

  return (
    <div className="stack">
      <h1>투자일지</h1>
      <p className="muted">거래 전 작성한 논리와 거래 후 복기를 모아볼 수 있습니다.</p>

      {journals.loading && <LoadingBlock label="투자일지를 불러오는 중입니다..." />}
      {journals.error && <ErrorBlock message={journals.error} onRetry={journals.reload} />}
      {journals.data && journals.data.length === 0 && (
        <EmptyBlock message="아직 작성한 투자일지가 없습니다. 종목 상세 화면에서 매수 전 투자일지를 작성해보세요." />
      )}

      <div className="stack">
        {journals.data?.map((j) => (
          <Link key={j.id} href={`/journal/${j.id}`} className="card" style={{ marginBottom: 0, textDecoration: "none" }}>
            <div className="row-between">
              <strong>{j.thesis ?? "(제목 없음)"}</strong>
              <span className="badge badge-virtual">
                {j.order_id ? (j.followed_plan === null ? "체결됨 · 복기 대기" : "복기 완료") : "거래 전"}
              </span>
            </div>
            {j.process_score !== null && (
              <p className="muted" style={{ margin: "4px 0 0" }}>과정 점수 {Number(j.process_score).toFixed(0)}점</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
