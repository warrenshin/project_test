import { test, expect, type Page } from "@playwright/test";

/**
 * 6~15강 콘텐츠 승인 절차 거버넌스 검증 + 퀴즈 선택지 순서 안정성 검증.
 *
 * 중요: 6~15강 10개 강의는 이제 전부 status=READY_FOR_REVIEW다(에이전트가 스스로
 * 승인하지 않음 — docs/content-review/lessons-06-15-review.md 참고). 따라서 이
 * 스펙은 더 이상 "7강을 공개 화면에서 완료한다" 같은 골든 패스 테스트를 6~15강으로
 * 수행하지 않는다 — 그렇게 하면 아직 승인되지 않은 콘텐츠가 화면에 노출된다는
 * 잘못된 전제 위에서 테스트하게 된다. 대신:
 * - 골든 패스(완료 -> 퀴즈 -> 채점 -> XP -> 새로고침 유지)는 이미 PUBLISHED 상태인
 *   1강("투자는 무엇인가")으로 검증한다.
 * - 6~15강 10개 전부가 목록·공개 API 어디에도 노출되지 않는지 확인한다.
 * - 퀴즈 선택지 표시 순서가 한 시도 내에서 안정적이고, 채점 후 정답 바인딩이
 *   표시 순서와 무관하게 정확하며, 재응시 시에만 다시 섞이는지 확인한다.
 */

const NEW_LESSON_TITLES = [
  "거래소와 장 운영시간",
  "시장가와 지정가",
  "호가·스프레드·유동성",
  "수수료·세금·환율",
  "투자수익률 계산",
  "복리의 효과와 한계",
  "변동성과 최대낙폭",
  "분산투자의 원리",
  "자산배분 기초",
  "시가총액과 기업가치",
];

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

test.describe("6~15강 콘텐츠 승인 거버넌스", () => {
  test("6~15강 10개 전부 학습 목록·공개 API 어디에도 노출되지 않는다", async ({ page }) => {
    await signUp(page, uniqueEmail("new-lessons-hidden"));

    await page.goto("/learn");
    for (const title of NEW_LESSON_TITLES) {
      await expect(page.getByRole("link", { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })).toHaveCount(0);
    }

    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100";
    const lessonsRes = await page.request.get(`${apiBase}/v1/learning/paths`);
    const paths = await lessonsRes.json();
    const titles: string[] = paths.flatMap((p: { courses: { modules: { lessons: { title: string }[] }[] }[] }) =>
      p.courses.flatMap((c) => c.modules.flatMap((m) => m.lessons.map((l) => l.title)))
    );
    for (const title of NEW_LESSON_TITLES) {
      expect(titles).not.toContain(title);
    }
    // 기존 1~5강은 여전히 노출되어야 한다(6~15강 미승인이 기존 콘텐츠를 건드리지 않았는지 확인).
    expect(titles).toContain("투자는 무엇인가");
  });
});

test.describe("골든 패스 (기존 PUBLISHED 강의로 검증 — 1강)", () => {
  test("1강 진입부터 퀴즈·XP·새로고침 유지까지 전체 흐름이 동작한다", async ({ page }) => {
    await signUp(page, uniqueEmail("lesson1"));

    await page.goto("/learn");
    const lessonLink = page.getByRole("link", { name: "투자는 무엇인가 5분" });
    await expect(lessonLink).toBeVisible();
    await lessonLink.click();

    await expect(page.getByRole("heading", { name: "투자는 무엇인가", exact: true })).toBeVisible();
    await expect(page.getByRole("note")).toContainText("교육용 콘텐츠이며");

    await page.getByRole("button", { name: "학습 완료로 표시" }).click();
    await expect(page.getByText(/XP 획득/)).toBeVisible();

    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    await expect(page.getByText("1. 저축과 투자의 가장 큰 차이는 무엇인가요?")).toBeVisible();

    await page.getByLabel("투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구한다").check();
    await page.getByLabel("미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위이다").check();

    await page.getByRole("button", { name: "제출하기" }).click();
    const resultBanner = page.getByText(/점수 \d+% · 합격/);
    await expect(resultBanner).toBeVisible();
    await expect(resultBanner).toContainText("XP");
    await expect(page.getByText("(정답)").first()).toBeVisible();

    await page.reload();
    await expect(page.getByText("이미 완료한 강의입니다.")).toBeVisible();
  });

  test("390px 모바일 뷰포트에서도 가로 스크롤 없이 표시된다", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signUp(page, uniqueEmail("lesson-mobile"));

    await page.goto("/learn");
    await expect(page.getByRole("link", { name: "투자는 무엇인가 5분" })).toBeVisible();
    await page.getByRole("link", { name: "투자는 무엇인가 5분" }).click();
    await expect(page.getByRole("heading", { name: "투자는 무엇인가", exact: true })).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
});

test.describe("퀴즈 선택지 순서 안정성", () => {
  test("한 시도 내에서는 순서가 고정되고, 채점은 표시 순서와 무관하게 정확하며, 재응시해야만 다시 섞인다", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await signUp(page, uniqueEmail("choice-order"));
    await page.goto("/learn");
    await page.getByRole("link", { name: "투자는 무엇인가 5분" }).click();
    await page.getByRole("button", { name: "학습 완료로 표시" }).click();
    await expect(page.getByText(/XP 획득/)).toBeVisible();

    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    const radioLabels = page.locator("label:has(input[type='radio'])");
    await expect(radioLabels).toHaveCount(8); // 2문항 x 4선택지

    // 1) DOM 순서 == 화면 세로 위치 순서 (CSS로 재정렬하지 않음 -> 키보드/스크린리더 순서와 시각 순서가 일치).
    const domOrderVsVisualOrder = await page.evaluate(() => {
      const labels = Array.from(document.querySelectorAll("label")).filter((l) => l.querySelector("input[type='radio']"));
      const withTop = labels.map((l) => l.getBoundingClientRect().top);
      const sorted = [...withTop].sort((a, b) => a - b);
      return withTop.every((v, i) => v === sorted[i]);
    });
    expect(domOrderVsVisualOrder).toBe(true);

    const orderBeforeSelect = await radioLabels.allTextContents();

    // 2) 오답 하나를 골라 재렌더링을 유발한다(체크 상태 변경) — 순서는 그대로 유지되어야 한다.
    await page.getByLabel("투자와 저축은 위험 수준이 동일하다").check();
    const orderAfterSelect = await radioLabels.allTextContents();
    expect(orderAfterSelect).toEqual(orderBeforeSelect);

    // 3) 두 번째 문항은 정답으로 고른다 -> 1문항 오답, 1문항 정답 (50% < 70% 합격선 -> 불합격 유도).
    await page.getByLabel("미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위이다").check();
    const orderBeforeSubmit = await radioLabels.allTextContents();
    expect(orderBeforeSubmit).toEqual(orderBeforeSelect); // 제출 직전까지도 순서 불변

    await page.getByRole("button", { name: "제출하기" }).click();
    await expect(page.getByText(/점수 \d+% · 미합격/)).toBeVisible();

    // 4) 채점 결과의 "(정답)" 표시는 선택지 표시 순서와 무관하게, 실제 정답 라벨 텍스트에 정확히 붙는다.
    const correctFeedback = page.locator("li", { hasText: "(정답)" }).first();
    await expect(correctFeedback).toContainText("투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구한다");

    // 5) 재응시(다시 풀기)를 누르면 새 시도로 취급되어 순서가 다시 섞일 수 있다 — 같은 항목 집합인지만 확인한다(섞임 자체는 확률적이라 강제하지 않음).
    await page.getByRole("button", { name: "다시 풀기" }).click();
    await expect(radioLabels).toHaveCount(8);
    const orderAfterRetry = await radioLabels.allTextContents();
    expect([...orderAfterRetry].sort()).toEqual([...orderBeforeSelect].sort());

    const hydrationErrors = consoleErrors.filter((e) => /hydration/i.test(e));
    expect(hydrationErrors).toEqual([]);
  });
});
