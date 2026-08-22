import { test, expect, type Page } from "@playwright/test";

/**
 * 7일 학습 챌린지 E2E 흐름:
 * 회원가입 -> 챌린지 소개/시작 -> Day1 미션(강의/퀴즈/목표) 완료 -> XP·배지 반영 ->
 * 새로고침 후 상태 유지 -> Day2(잠긴 Day) 접근 차단 -> 모바일 뷰포트 -> 에러/재시도.
 *
 * 정답 선택지는 시드 마이그레이션에서 각 문항의 첫 번째 선택지로 고정되어 있다.
 */

const uniqueEmail = () => `e2e-challenge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
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

test.describe("7일 학습 챌린지", () => {
  test("시작부터 Day1 완료·XP·배지·새로고침 유지까지 전체 흐름이 동작한다", async ({ page }) => {
    const email = uniqueEmail();
    await signUp(page, email);

    // 1) 챌린지 소개 화면 -> 시작
    await page.goto("/challenge");
    await expect(page.getByRole("heading", { name: "7일 투자 학습 챌린지" })).toBeVisible();
    await expect(page.getByText(/수익률이나 거래 횟수/).first()).toBeVisible();
    await page.getByRole("button", { name: "7일 챌린지 시작하기" }).click();
    await expect(page.getByText("7일 진행 지도")).toBeVisible();
    await expect(page.getByText("Day 1 / 7")).toBeVisible();

    // 2) Day1 강의 미션: 강의로 이동 -> 완료 -> 되돌아와 완료 확인
    await page.getByRole("link", { name: "강의로 이동" }).first().click();
    await expect(page.getByRole("heading", { name: "투자는 무엇인가", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "학습 완료로 표시" }).click();
    await expect(page.getByText(/XP 획득/)).toBeVisible();

    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    await page.getByLabel("투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구한다").check();
    await page.getByLabel("미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위이다").check();
    await page.getByRole("button", { name: "제출하기" }).click();
    await expect(page.getByText(/합격/)).toBeVisible();

    await page.goto("/challenge");
    await page.getByRole("button", { name: "완료 확인" }).first().click();
    await expect(page.getByText(/미션을 완료했습니다/)).toBeVisible();
    // 첫 강의 완료로 "첫걸음" 배지를 즉시 획득한다.
    await expect(page.getByText("🏅 첫걸음")).toBeVisible();

    // 3) Day1 퀴즈 미션 완료 확인
    await page.getByRole("button", { name: "완료 확인" }).first().click();
    await expect(page.getByText(/미션을 완료했습니다/)).toBeVisible();

    // 4) Day1 목표 미션(GOAL_NOTE) 작성
    await page.getByRole("textbox").fill("이번 주에는 투자 원칙을 세우고 지켜보겠습니다");
    await page.getByRole("button", { name: "저장하고 완료 확인" }).click();
    await expect(page.getByText("이 Day의 모든 필수 미션을 완료했습니다!")).toBeVisible();

    // 5) 진행 상황 갱신 확인 — 누적 XP, Day 완료 표시
    await expect(page.getByText(/누적 XP 35/)).toBeVisible();
    await expect(page.getByText("완료한 Day 1개 / 7개")).toBeVisible();

    // 6) 배지 화면에서 실제로 획득했는지 확인
    await page.goto("/badges");
    await expect(page.getByText("🏅 첫걸음")).toBeVisible();
    await expect(page.getByText("획득함").first()).toBeVisible();

    // 7) 홈 화면 위젯에도 오늘 진행 상황이 반영된다 (수익률/PnL은 표시하지 않음)
    await page.goto("/");
    await expect(page.getByText("7일 챌린지 · Day 1/7")).toBeVisible();
    await expect(page.getByText(/오늘 미션 3\/3개 완료/)).toBeVisible();

    // 8) 새로고침 후에도 챌린지 진행 상태가 유지된다
    await page.goto("/challenge");
    await page.reload();
    await expect(page.getByText("Day 1 / 7")).toBeVisible();
    await expect(page.getByText(/누적 XP 35/)).toBeVisible();
    await expect(page.getByText("1강 학습: 투자는 무엇인가")).toBeVisible();

    // 9) Day2는 아직 잠겨 있어 미션을 열거나 인증할 수 없다
    const day2Row = page.getByRole("button", { name: /Day 2 · 주문 방식 이해/ });
    await expect(day2Row).toBeDisabled();
    await expect(page.getByText("잠김").first()).toBeVisible();
  });

  test("모바일 뷰포트(390px)에서도 챌린지 화면이 올바르게 렌더링된다", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const email = uniqueEmail();
    await signUp(page, email);

    await page.goto("/challenge");
    await expect(page.getByRole("heading", { name: "7일 투자 학습 챌린지" })).toBeVisible();
    // 페이지가 가로 스크롤을 만들지 않는지 확인한다.
    const hasHorizontalScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasHorizontalScroll).toBe(false);

    await page.getByRole("button", { name: "7일 챌린지 시작하기" }).click();
    await expect(page.getByText("7일 진행 지도")).toBeVisible();
    const hasHorizontalScrollAfterStart = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
    );
    expect(hasHorizontalScrollAfterStart).toBe(false);
  });

  test("챌린지 정보를 불러오지 못하면 에러 화면과 재시도 버튼이 표시된다", async ({ page }) => {
    const email = uniqueEmail();
    await signUp(page, email);

    let shouldFail = true;
    await page.route("**/v1/me/challenges/active", (route) => {
      if (shouldFail) {
        route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "서버 오류" }) });
      } else {
        route.continue();
      }
    });

    await page.goto("/challenge");
    await expect(page.getByText("문제가 발생했습니다")).toBeVisible();
    const retryButton = page.getByRole("button", { name: "다시 시도" });
    await expect(retryButton).toBeVisible();

    shouldFail = false;
    await retryButton.click();
    await expect(page.getByRole("heading", { name: "7일 투자 학습 챌린지" })).toBeVisible();
  });
});
