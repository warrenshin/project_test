import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // production Docker 이미지를 최소화하기 위해 self-contained 서버 번들을
  // 생성한다(.next/standalone) — 런타임에 전체 node_modules가 필요 없다.
  output: "standalone",
};

export default nextConfig;
