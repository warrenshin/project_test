import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const WEB_PORT = 3100;
const API_PORT = 8100;

// 이 저장소를 개발한 샌드박스에는 Chromium이 고정 경로에 미리 설치되어 있어
// `playwright install`을 건너뛴다. 그 경로가 없는 환경(CI 러너, 다른 개발자
// PC 등)에서는 Playwright가 관리하는 일반 설치 경로를 그대로 쓴다.
const SANDBOX_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
const chromiumExecutablePath = fs.existsSync(SANDBOX_CHROMIUM_PATH) ? SANDBOX_CHROMIUM_PATH : undefined;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
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
  webServer: [
    {
      // 데모 시드 시세는 한 번 오래되면(기본 900초) 주문이 거부되므로(6.7, 12.3),
      // 서버를 띄우기 전에 최신 bar의 as_of를 현재 시각으로 새로고침한다.
      command:
        "python3 -m scripts.refresh_demo_market_data && uvicorn app.main:app --host 0.0.0.0 --port " + API_PORT,
      cwd: path.resolve(__dirname, "../api"),
      port: API_PORT,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        DATABASE_URL: "postgresql+psycopg://app:app@localhost:5432/investment_learning",
        CORS_ALLOWED_ORIGINS_RAW: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`,
      },
    },
    {
      command: `next dev -p ${WEB_PORT}`,
      cwd: __dirname,
      port: WEB_PORT,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        NEXT_PUBLIC_API_BASE_URL: `http://localhost:${API_PORT}`,
      },
    },
  ],
});
