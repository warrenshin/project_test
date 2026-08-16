import { test, expect, type Page } from "@playwright/test";

/**
 * 핵심 E2E 흐름:
 * 회원가입 -> 1강 학습 -> 퀴즈 제출/XP -> SK하이닉스 검색 -> 거래 전 일지 ->
 * 가상 시장가 매수 -> 포트폴리오 반영 -> 거래 후 복기 -> 규칙 기반 AI 코칭 확인
 * 새로고침과 재로그인 후에도 데이터가 유지되는지도 함께 검증한다(요구사항 7).
 *
 * 정답 선택지는 시드 마이그레이션(6f55307ed5e8_seed_first_5_lessons_with_quizzes)에서
 * 각 문항의 첫 번째 선택지로 고정되어 있어, 텍스트로 직접 선택할 수 있다.
 */

const uniqueEmail = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
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
  await expect(page.getByRole("heading", { name: /안녕하세요/ })).toBeVisible();
}

async function logIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL("/");
}

test.describe("핵심 E2E 사용자 흐름", () => {
  test("회원가입부터 AI 코칭까지 전체 흐름이 동작한다", async ({ page }) => {
    const email = uniqueEmail();

    // 1) 회원가입
    await signUp(page, email);

    // 2) 1강 학습
    await page.goto("/learn");
    const firstLessonLink = page.getByRole("link", { name: /투자는 무엇인가/ });
    await expect(firstLessonLink).toBeVisible();
    await firstLessonLink.click();
    await expect(page.getByRole("heading", { name: "투자는 무엇인가", exact: true })).toBeVisible();
    await expect(page.getByText("학습 목표")).toBeVisible();

    await page.getByRole("button", { name: "학습 완료로 표시" }).click();
    await expect(page.getByText(/XP 획득/)).toBeVisible();

    // 3) 퀴즈 제출과 XP 획득
    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    await expect(page.getByText("1. 저축과 투자의 가장 큰 차이는 무엇인가요?")).toBeVisible();

    await page.getByLabel("투자는 원금 손실 위험을 감수하고 더 높은 기대수익을 추구한다").check();
    await page.getByLabel("미래의 더 큰 가치를 위해 현재 자원을 특정 자산에 투입하는 행위이다").check();

    await page.getByRole("button", { name: "제출하기" }).click();
    const quizResultBanner = page.getByText(/점수 \d+% · 합격/);
    await expect(quizResultBanner).toBeVisible();
    await expect(quizResultBanner).toContainText("XP");

    // 4) SK하이닉스 종목 검색
    await page.goto("/market");
    await page.getByPlaceholder(/종목명 또는 코드/).fill("SK하이닉스");
    await page.getByRole("button", { name: "검색" }).click();
    const skHynixLink = page.getByRole("link", { name: /SK하이닉스/ });
    await expect(skHynixLink).toBeVisible();
    await skHynixLink.click();
    await expect(page.getByRole("heading", { name: "SK하이닉스" })).toBeVisible();
    await expect(page.getByText("000660")).toBeVisible();

    // 5) 거래 전 투자일지 작성
    await page.getByRole("link", { name: "투자일지 작성 후 매수하기" }).click();
    await expect(page.getByRole("heading", { name: "거래 전 투자일지" })).toBeVisible();
    await page.getByLabel("투자 논리 (필수)").fill("메모리 반도체 업황 개선 기대");
    await page.getByLabel("근거 (한 줄에 하나씩, 최대 3개)").fill("메모리 가격 반등\nAI 서버 수요 증가");
    await page.getByLabel("반대 근거 (한 줄에 하나씩)").fill("업황 사이클 둔화 위험");
    await page.getByLabel("계획 비중 (%)").fill("5");
    await page.getByRole("button", { name: "일지 저장하고 주문으로 이동" }).click();

    // 6) 가상 시장가 매수
    await expect(page.getByRole("heading", { name: "모의 주문" })).toBeVisible();
    await expect(page.getByText("가상자금 기반 모의투자")).toBeVisible();
    await expect(page.getByText("투자일지와 연결되어")).toBeVisible();
    await page.getByLabel("수량 (시장가 주문)").fill("1");
    await page.getByRole("button", { name: "주문 미리보기" }).click();
    await expect(page.getByText("예상 체결가")).toBeVisible();
    await page.getByRole("button", { name: "가상자금으로 매수 확정" }).click();

    // 7) 포트폴리오 반영 확인 (일지 상세로 리디렉션된 뒤 포트폴리오에서 재확인)
    await expect(page).toHaveURL(/\/journal\/.+orderConfirmed=1/);
    await page.goto("/portfolio");
    await expect(page.getByText("000660")).toBeVisible();

    // 8) 거래 후 복기
    await page.goto("/journal");
    await page.getByText("메모리 반도체 업황 개선 기대").click();
    await expect(page.getByRole("heading", { name: "거래 후 복기" })).toBeVisible();
    await page.getByLabel("계획대로 실행했나요?").selectOption("true");
    await page.getByLabel("기대와 실제 결과의 차이").fill("예상과 비슷하게 흘러갔다");
    await page.getByRole("button", { name: "복기 저장" }).click();
    await expect(page.getByText("계획대로 실행", { exact: true })).toBeVisible();

    // 9) 규칙 기반 AI 코칭 확인 (이 환경엔 ANTHROPIC_API_KEY가 없어 폴백 경로만 검증 가능)
    await page.getByRole("button", { name: "AI 코칭 확인" }).click();
    await expect(page.getByText(/규칙 기반 폴백 코칭으로 대체/)).toBeVisible();

    // 10) 새로고침 후에도 로그인/데이터 유지 확인
    await page.reload();
    await expect(page.getByRole("heading", { name: "투자일지" })).toBeVisible();
    await expect(page.getByText("계획대로 실행", { exact: true })).toBeVisible();

    // 11) 재로그인 후에도 데이터 유지 확인
    await page.evaluate(() => window.localStorage.clear());
    await logIn(page, email);
    await page.goto("/portfolio");
    await expect(page.getByText("000660")).toBeVisible();
  });
});
