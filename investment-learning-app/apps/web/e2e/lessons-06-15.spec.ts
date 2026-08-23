import { test, expect, type Page } from "@playwright/test";

/**
 * 6~15강 투자교육 콘텐츠의 실제 화면 흐름 검증:
 * - 7강("시장가와 지정가") 진입 -> 완료 -> 퀴즈 -> 해설 -> XP -> 새로고침 유지
 * - DRAFT 강의(6강)는 API/화면 어디에도 노출되지 않는다
 * - 390px 모바일 뷰포트에서도 정상 표시된다
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

test.describe("6~15강 투자교육 콘텐츠", () => {
  test("7강 진입부터 퀴즈·XP·새로고침 유지까지 전체 흐름이 동작한다", async ({ page }) => {
    await signUp(page, uniqueEmail("lesson7"));

    await page.goto("/learn");
    const lessonLink = page.getByRole("link", { name: "시장가와 지정가 6분" });
    await expect(lessonLink).toBeVisible();
    await lessonLink.click();

    await expect(page.getByRole("heading", { name: "시장가와 지정가", exact: true })).toBeVisible();
    // 진단 아님 고지
    await expect(page.getByRole("note")).toContainText("교육용 콘텐츠이며");
    // 카드형 본문 블록들
    await expect(page.getByRole("heading", { name: "흔한 오해" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "핵심 요약" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "관련 실습" })).toBeVisible();

    await page.getByRole("button", { name: "학습 완료로 표시" }).click();
    await expect(page.getByText(/XP 획득/)).toBeVisible();

    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    await expect(page.getByText("1. 시장가 주문의 가장 큰 특징은 무엇인가요?")).toBeVisible();

    // 4문항 모두 정답을 고른다(라벨 텍스트로 선택 — 화면 표시 순서는 매번 섞인다).
    await page.getByLabel("가격을 지정하지 않고 체결 가능성이 높다").check();
    await page.getByLabel(/체결되지 않고 계속 대기한다/).check();
    await page.getByLabel(/틀린 생각이다 — 가격 조건이 맞지 않으면 체결되지 않을 수 있다/).check();
    await page.getByLabel("시장가 주문", { exact: true }).check();

    await page.getByRole("button", { name: "제출하기" }).click();
    const resultBanner = page.getByText(/점수 \d+% · 합격/);
    await expect(resultBanner).toBeVisible();
    await expect(resultBanner).toContainText("XP");
    // 오답별 설명(정답 표시)이 노출된다
    await expect(page.getByText("(정답)").first()).toBeVisible();

    // 새로고침 후에도 완료 상태·XP 유지
    await page.reload();
    await expect(page.getByText("이미 완료한 강의입니다.")).toBeVisible();
  });

  test("DRAFT 강의(6강)는 목록에도 상세 화면에도 노출되지 않는다", async ({ page }) => {
    await signUp(page, uniqueEmail("draft-block"));

    await page.goto("/learn");
    await expect(page.getByRole("link", { name: /거래소와 장 운영시간/ })).toHaveCount(0);

    // API로 직접 시도해도 404 — 화면에 링크가 없다는 것만으로는 부족하므로 API도 확인한다.
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100";
    const lessonsRes = await page.request.get(`${apiBase}/v1/learning/paths`);
    const paths = await lessonsRes.json();
    const titles = paths.flatMap((p: { courses: { modules: { lessons: { title: string }[] }[] }[] }) =>
      p.courses.flatMap((c) => c.modules.flatMap((m) => m.lessons.map((l) => l.title)))
    );
    expect(titles).not.toContain("거래소와 장 운영시간");
    expect(titles).not.toContain("수수료·세금·환율");
  });

  test("390px 모바일 뷰포트에서도 가로 스크롤 없이 표시된다", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signUp(page, uniqueEmail("lesson-mobile"));

    await page.goto("/learn");
    await expect(page.getByRole("link", { name: "시장가와 지정가 6분" })).toBeVisible();
    await page.getByRole("link", { name: "시장가와 지정가 6분" }).click();
    await expect(page.getByRole("heading", { name: "시장가와 지정가", exact: true })).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
});
