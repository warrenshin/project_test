"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { getBiasReport } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";

export default function MePage() {
  const { logout } = useAuth();
  const bias = useAsync(() => getBiasReport(), []);

  return (
    <div className="stack">
      <h1>마이</h1>

      <div className="card">
        <h2>성장 리포트 — 관찰된 거래 패턴</h2>
        <p className="muted">{bias.data?.note ?? "행동편향은 진단이 아니라 관찰된 거래 패턴으로만 표시됩니다."}</p>
        {bias.loading && <LoadingBlock label="편향 리포트를 불러오는 중입니다..." />}
        {bias.error && <ErrorBlock message={bias.error} onRetry={bias.reload} />}
        {bias.data && bias.data.observations.length === 0 && (
          <EmptyBlock message="아직 뚜렷하게 관찰된 거래 패턴이 없습니다." />
        )}
        {bias.data && bias.data.observations.length > 0 && (
          <div className="stack">
            {bias.data.observations.map((o) => (
              <div key={o.pattern} className="card" style={{ marginBottom: 0 }}>
                <strong>{o.pattern}</strong>
                <p style={{ margin: "4px 0" }}>{o.description}</p>
                <p className="muted" style={{ margin: 0 }}>제안: {o.coaching_direction}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card stack">
        <Link href="/journal" className="btn btn-block">
          내 투자일지 보기
        </Link>
        <button className="btn btn-block" onClick={logout} type="button">
          로그아웃
        </button>
      </div>
    </div>
  );
}
