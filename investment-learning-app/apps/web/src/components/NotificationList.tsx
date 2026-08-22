"use client";

import Link from "next/link";
import { useState } from "react";
import { getMyNotifications } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import type { NotificationResponse } from "@/lib/types";

const ICON: Record<NotificationResponse["type"], string> = {
  LESSON_DUE: "📘",
  TRADE_REVIEW_DUE: "📝",
  CHALLENGE_STEP_DUE: "🧭",
  BADGE_EARNED: "🏅",
};

/** 실제 푸시 알림이 아니라, 지금 화면에 보여줄 인앱 알림 목록이다(홈 화면
 * 전용). 매수 유도·조급함을 자극하는 문구는 서버가애초에 만들지 않는다 —
 * 여기서는 서버가 준 문구를 그대로 보여줄 뿐이다. */
export function NotificationList() {
  const notifications = useAsync(() => getMyNotifications(), []);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());

  if (notifications.loading || notifications.error) return null;
  const items = (notifications.data ?? []).filter((_, i) => !dismissed.has(i));
  if (items.length === 0) return null;

  return (
    <div className="stack" aria-label="알림">
      {items.map((n, i) => (
        <div key={i} className="banner banner-info row-between">
          <Link href={n.href} style={{ textDecoration: "none", flex: 1 }}>
            <span aria-hidden="true">{ICON[n.type]}</span> <strong>{n.title}</strong>
            <p style={{ margin: "2px 0 0" }}>{n.body}</p>
          </Link>
          <button
            className="btn"
            onClick={() => setDismissed((prev) => new Set(prev).add(i))}
            type="button"
            aria-label="알림 닫기"
          >
            닫기
          </button>
        </div>
      ))}
    </div>
  );
}
