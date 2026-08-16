"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "홈" },
  { href: "/learn", label: "학습" },
  { href: "/market", label: "모의투자" },
  { href: "/journal", label: "일지" },
  { href: "/me", label: "마이" },
];

export function TabBar() {
  const pathname = usePathname();
  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => {
        const current = tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href);
        return (
          <Link key={tab.href} href={tab.href} aria-current={current ? "page" : undefined}>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
