import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // production Docker 이미지를 최소화하기 위해 self-contained 서버 번들을
  // 생성한다(.next/standalone) — 런타임에 전체 node_modules가 필요 없다.
  // 단, Vercel은 자체 서버리스 번들링 파이프라인을 쓰기 때문에 이 옵션과
  // 충돌한다(빌드 마지막 단계에서 .next/next-server.js.nft.json을 찾다가
  // ENOENT로 실패함) — Vercel 빌드 환경에서 자동으로 설정되는 VERCEL
  // 환경변수를 보고 그때만 끈다. 로컬 Docker Compose 빌드는 계속 standalone을
  // 쓴다.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
