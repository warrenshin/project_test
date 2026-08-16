import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const WEB_PORT = 3100;
const API_PORT = 8100;

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
        launchOptions: { executablePath: "/opt/pw-browsers/chromium" },
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
