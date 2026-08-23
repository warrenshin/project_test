import { test, expect, type Page } from "@playwright/test";

/**
 * "마이" 화면의 행동편향 리포트(성장 리포트) — 감사 지적 사항 검증:
 * - "진단 아님" 고지, 데이터 부족 상태, 근거·한계·자가점검 질문 노출
 * - 실제로 신호가 감지된 경우 상위 신호로 보여지고, 확인(acknowledge) 가능
 * - 매수/매도 지시, 구체적 손절가, "나쁜 투자자" 낙인, 빨간색 단독 위험 표시
 *   같은 금지 표현이 없음
 * - 390px 모바일 뷰포트에서도 가로 스크롤 없이 정상 표시
 */

const uniqueEmail = (tag: string) => `e2e-${tag}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
const PASSWORD = "correct-horse-battery-staple";

async function signUp(page: Page, email: string) {
  await page.goto("/signup");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호 (8자 이상)").fill(PASSWORD);
  await page.getByLabel("생년월일").fill("2000-01-01");
  await page.getByLabel("(필수) 이용약관에 동의합니다").check();
  await page.getByLabel("(필수) 개인정보 처리방침에 동의합니다").check();
  await page.getByRole("button", { name: "가상자금으로 시작하기" }).click();
  await expect(page).toHaveURL("/");
}

const FORBIDDEN_PHRASES = [
  "매수하세요",
  "매도하세요",
  "지금 파세요",
  "지금 사세요",
  "나쁜 투자자",
  "손절가는",
];

test.describe("성장 리포트 — 행동편향 화면", () => {
  test("신호가 없는 신규 사용자: 진단 아님 고지 + 데이터 부족 상태 표시", async ({ page }) => {
    await signUp(page, uniqueEmail("nobias"));
    await page.goto("/me");

    await expect(page.getByText("성장 리포트")).toBeVisible();
    await expect(page.getByText("의학적 진단이나 심리 평가가 아닙니다")).toBeVisible();
    await expect(page.getByText("아직 뚜렷하게 관찰된 거래 패턴이 없습니다")).toBeVisible();

    // 7종 전체가 "나머지 항목"으로 접혀 있고, 펼치면 데이터 부족 상태가 보인다.
    const moreToggle = page.getByText(/나머지 7개 항목 더 보기/);
    await expect(moreToggle).toBeVisible();
    await moreToggle.click();
    await expect(page.getByText("데이터 부족").first()).toBeVisible();

    for (const phrase of FORBIDDEN_PHRASES) {
      await expect(page.getByText(phrase)).toHaveCount(0);
    }
  });

  test("과잉매매가 실제로 감지되면 상위 신호로 보이고, 확인 처리를 할 수 있다", async ({ page }) => {
    const email = uniqueEmail("overtrade");
    await signUp(page, email);

    // SK하이닉스를 짧은 시간 안에 5회 연속 매수해 과잉매매 임계값(24시간 내 5건)을 채운다.
    // UI 클릭 대신 로그인된 브라우저 컨텍스트의 쿠키를 공유하는 page.request로 직접
    // 호출한다 — 화면 클릭 반복은 이 테스트의 목적(리포트 화면 검증)에 비해 불필요하다.
    const portfolioRes = await page.request.get(`${API_BASE}/v1/me/portfolio`);
    expect(portfolioRes.ok()).toBeTruthy();
    const portfolioBody = await portfolioRes.json();
    const portfolioId = portfolioBody.id as string;

    const searchRes = await page.request.get(`${API_BASE}/v1/instruments/search?q=${encodeURIComponent("SK하이닉스")}`);
    expect(searchRes.ok()).toBeTruthy();
    const results = await searchRes.json();
    const instrumentId = results[0].id as string;

    for (let i = 0; i < 5; i++) {
      const orderRes = await page.request.post(`${API_BASE}/v1/portfolios/${portfolioId}/orders`, {
        data: { instrument_id: instrumentId, side: "BUY", order_type: "MARKET", quantity: "1" },
        // CSRF Origin 검증 미들웨어(app.core.csrf)를 통과하려면 허용된 Origin이 필요하다
        // (tests/conftest.py의 공유 TestClient가 하는 것과 동일한 이유).
        headers: { "Idempotency-Key": `bias-e2e-${email}-${i}`, Origin: "http://localhost:3100" },
      });
      expect(orderRes.ok()).toBeTruthy();
    }

    await page.goto("/me");
    await expect(page.getByText("지금 살펴보면 좋을 신호")).toBeVisible();

    const overtradingCard = page.getByTestId("bias-card-OVERTRADING");
    await expect(overtradingCard.getByText("과잉매매 의심 패턴")).toBeVisible();
    await expect(overtradingCard.getByText(/심각도/)).toBeVisible();
    await expect(overtradingCard.getByText("판단 가능")).toBeVisible();

    // 근거·한계 펼치기
    await overtradingCard.getByText("근거·한계 자세히 보기").click();
    await expect(overtradingCard.getByText("이 판단의 한계:")).toBeVisible();
    await expect(overtradingCard.getByText("스스로 점검해보기:")).toBeVisible();

    // 확인 처리
    const ackButton = overtradingCard.getByRole("button", { name: "확인했어요" });
    await expect(ackButton).toBeVisible();
    await ackButton.click();
    await expect(overtradingCard.getByText(/확인함 \(/)).toBeVisible();

    for (const phrase of FORBIDDEN_PHRASES) {
      await expect(page.getByText(phrase)).toHaveCount(0);
    }
  });

  test("390px 모바일 뷰포트에서도 가로 스크롤 없이 표시된다", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signUp(page, uniqueEmail("mobile"));
    await page.goto("/me");

    await expect(page.getByText("성장 리포트")).toBeVisible();
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
});

// playwright.config.ts에서 webServer로 NEXT_PUBLIC_API_BASE_URL을 8100 포트로 고정한다.
const API_BASE = "http://localhost:8100";
