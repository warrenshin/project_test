"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoadingBlock } from "./States";

export function ProtectedPage({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status === "loading") return <LoadingBlock label="세션을 확인하는 중입니다..." />;
  if (status === "unauthenticated") return null;
  return <>{children}</>;
}
