# --- deps: package-lock.json에 고정된 버전 그대로 설치 ---
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- builder: production build (standalone 서버 번들 생성) ---
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 브라우저가 직접 호출할 API 주소. NEXT_PUBLIC_ 접두사가 붙은 값은 비밀정보가
# 아니라 클라이언트 번들에 그대로 노출되는 공개 설정이므로 build arg로 받는다
# (실제 비밀값은 이 이미지에 어떤 방식으로도 넣지 않는다).
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

# --- runtime: standalone 서버 산출물만 담은 최소 이미지 ---
FROM node:22-slim AS runtime
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
COPY --from=builder --chown=app:app /app/public ./public

USER app

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
