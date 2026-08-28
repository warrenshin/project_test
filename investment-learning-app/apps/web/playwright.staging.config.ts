import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";

/**
 * 로컬 스테이징 전용 Playwright 설정.
 *
 * 기존 playwright.config.ts(개발 DB + 자체 webServer 기동)와는 완전히
 * 분리되어 있으며 서로의 설정을 참조하지 않는다. 이 설정은:
 *   - webServer를 전혀 기동하지 않는다 — 반드시 사전에 떠 있는 로컬 스테이징
 *     (investment-learning-app/scripts/staging_up.sh 로 기동한
 *     docker-compose.yml + docker-compose.staging.yml 스택)을 대상으로만
 *     동작한다.
 *   - web은 http://localhost:3001, API는 http://localhost:8001을 기본값으로
 *     사용한다(STAGING_WEB_BASE_URL / STAGING_API_BASE_URL로 덮어쓸 수 있음).
 *   - 개발 전용 포트(3000/8000/5432)나 localhost/127.0.0.1이 아닌 호스트
 *     (production/클라우드 등)는 STAGING_E2E_ALLOW_REMOTE=true를 명시적으로
 *     설정하지 않는 한 설정 로드 시점에 즉시 실패한다("실패 시 닫힌다").
 *
 * 실행 방법(둘 중 하나):
 *   npm run test:e2e:staging                (apps/web/ 안에서)
 *   scripts/staging_e2e_run.sh               (investment-learning-app/ 안에서 —
 *     게시 상태/감사기록이 실행 전후 동일한지까지 함께 확인하는 래퍼)
 * 자세한 내용은 README의 "스테이징 E2E" 절 참고.
 */

const DEFAULT_WEB_BASE_URL = "http://localhost:3001";
const DEFAULT_API_BASE_URL = "http://localhost:8001";
const DEV_ONLY_PORTS = new Set(["3000", "8000", "5432"]);

function resolveAndValidateBaseUrl(envVarName: string, defaultUrl: string): string {
  const raw = process.env[envVarName] ?? defaultUrl;

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`[playwright.staging.config] ${envVarName}="${raw}"이(가) 올바른 URL이 아닙니다.`);
  }

  const isLocalHost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  const allowRemote = process.env.STAGING_E2E_ALLOW_REMOTE === "true";
  if (!isLocalHost && !allowRemote) {
    throw new Error(
      `[playwright.staging.config] ${envVarName}="${raw}"은(는) localhost/127.0.0.1이 아닙니다. ` +
        "스테이징 E2E는 production/클라우드에 접근하지 않는 것이 기본 정책입니다. " +
        "정말로 원격 스테이징을 대상으로 실행하려는 것이 맞다면 " +
        "STAGING_E2E_ALLOW_REMOTE=true를 명시적으로 설정한 뒤 다시 실행하세요."
    );
  }

  if (isLocalHost && DEV_ONLY_PORTS.has(parsed.port)) {
    throw new Error(
      `[playwright.staging.config] ${envVarName}="${raw}"이(가) 개발 전용 포트(${parsed.port})를 ` +
        "가리킵니다. 스테이징 E2E는 개발 스택(웹 3000 / API 8000 / DB 5432)에 접근할 수 없습니다. " +
        "로컬 스테이징 포트(웹 3001 / API 8001)를 사용하세요."
    );
  }

  return raw;
}

export const STAGING_WEB_BASE_URL = resolveAndValidateBaseUrl("STAGING_WEB_BASE_URL", DEFAULT_WEB_BASE_URL);
export const STAGING_API_BASE_URL = resolveAndValidateBaseUrl("STAGING_API_BASE_URL", DEFAULT_API_BASE_URL);

// 이 저장소를 개발한 샌드박스에는 Chromium이 고정 경로에 미리 설치되어 있다
// (기존 playwright.config.ts와 동일한 관례를 그대로 따른다).
const SANDBOX_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
const chromiumExecutablePath = fs.existsSync(SANDBOX_CHROMIUM_PATH) ? SANDBOX_CHROMIUM_PATH : undefined;

export default defineConfig({
  testDir: "./e2e-staging",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  // webServer 의도적으로 미설정 — 이미 떠 있는 로컬 스테이징을 그대로 사용한다.
  use: {
    baseURL: STAGING_WEB_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {},
      },
    },
  ],
});
