"use client";

import { useState } from "react";
import { getBadgeDefinitions, getMyBadges } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "@/components/States";
import type { BadgeDefinitionResponse, UserBadgeResponse } from "@/lib/types";

export default function BadgesPage() {
  const badges = useAsync(
    () => Promise.all([getBadgeDefinitions(), getMyBadges()]),
    []
  );
  const [selected, setSelected] = useState<BadgeDefinitionResponse | null>(null);

  if (badges.loading) return <LoadingBlock label="배지를 불러오는 중입니다..." />;
  if (badges.error) return <ErrorBlock message={badges.error} onRetry={badges.reload} />;

  const [allBadges, myBadges] = badges.data!;
  const earnedByCode = new Map<string, UserBadgeResponse>(myBadges.map((b) => [b.code, b]));

  return (
    <div className="stack">
      <h1>배지</h1>
      <p className="muted">
        수익률이나 거래 횟수로 얻는 배지는 없습니다. 학습을 끝내고, 원칙을 지키고,
        복기하는 과정에서 자연스럽게 쌓입니다.
      </p>

      {allBadges.length === 0 && <EmptyBlock message="아직 등록된 배지가 없습니다." />}

      <div className="stack">
        {allBadges.map((badge) => {
          const earned = earnedByCode.get(badge.code);
          return (
            <button
              key={badge.code}
              className="card"
              style={{ textAlign: "left", cursor: "pointer", opacity: earned ? 1 : 0.55 }}
              onClick={() => setSelected(badge)}
              type="button"
            >
              <div className="row-between">
                <strong>{earned ? "🏅" : "🔒"} {badge.title}</strong>
                {earned && <span className="badge badge-earned">획득함</span>}
              </div>
              {badge.description && <p className="muted" style={{ margin: "4px 0 0" }}>{badge.description}</p>}
              {earned && (
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  {new Date(earned.earned_at).toLocaleDateString("ko-KR")} 획득
                </p>
              )}
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="card" role="dialog" aria-label={`${selected.title} 배지 상세`}>
          <div className="row-between">
            <h2>{earnedByCode.get(selected.code) ? "🏅" : "🔒"} {selected.title}</h2>
            <button className="btn" onClick={() => setSelected(null)} type="button" aria-label="닫기">
              닫기
            </button>
          </div>
          <p>{selected.description}</p>
          {earnedByCode.get(selected.code) ? (
            <p className="muted" style={{ margin: 0 }}>
              {new Date(earnedByCode.get(selected.code)!.earned_at).toLocaleString("ko-KR")}에 획득했습니다.
            </p>
          ) : (
            <p className="muted" style={{ margin: 0 }}>아직 획득하지 않았습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}
