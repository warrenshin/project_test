import { test, expect } from "@playwright/test";
import { STAGING_API_BASE_URL } from "../playwright.staging.config";
import {
  CONTENT_BLOCK_LABELS,
  FORBIDDEN_INVESTMENT_PHRASES,
  LESSON_CODE_WITHOUT_SOURCE_URL,
  PUBLISHED_NEW_LESSON_CODES,
  PUBLISHED_NEW_LESSON_TITLES,
  assertNoHorizontalOverflow,
  fetchLearningPaths,
  flattenLessons,
  signUpStagingTestUser,
  uniqueStagingEmail,
} from "./support";

/**
 * 로컬 스테이징에 게시된 lesson-06~15(사람 검수자 warrenshin이 승인·게시 완료)를
 * 대상으로 하는 전용 E2E. 반드시 `npx playwright test -c playwright.staging.config.ts`
 * (또는 scripts/staging_e2e_run.sh)로만 실행한다 — 기본 `npx playwright test`는
 * 여전히 기존 playwright.config.ts(개발 DB + 자체 webServer)를 사용한다.
 *
 * 이 스펙이 하지 않는 것(의도적):
 *  - lesson_review_audits/lessons.status/review_status를 직접 바꾸지 않는다
 *    (모든 요청은 읽기 전용 GET이거나, 로그인·퀴즈 응시 같은 일반 사용자 액션뿐).
 *  - 실제 투자 주문(/v1/orders 등)을 생성하지 않는다.
 *  - 매 실행 UUID 기반 신규 이메일로만 가입한다 — 기존 사용자/진도 데이터를 전혀
 *    사용하지 않는다. 생성된 테스트 계정과 그 진도·퀴즈 응시 기록은 정리되지 않고
 *    남는다(로컬 스테이징은 언제든 scripts/staging_reset_data.sh로 초기화 가능한
 *    일회성 데이터이므로 허용 — README 참고). 고유 이메일이므로 기존 데이터와
 *    충돌하지 않는다.
 *  - lesson-06~15 게시 상태·감사기록이 실행 전후 동일한지는 scripts/staging_e2e_run.sh
 *    래퍼가 DB를 직접(읽기 전용 SELECT로만) 대조해 별도로 보증한다 — 브라우저
 *    테스트 자체는 공개 API 레벨에서만 회귀를 재확인한다(아래 마지막 describe).
 */

test.describe("게시 상태 회귀 확인 (API 레벨)", () => {
  test("lesson-06~15와 lesson-01~05가 모두 공개 API에 그대로 노출된다", async ({ request }) => {
    const lessons = flattenLessons(await fetchLearningPaths(request));
    const codes = new Set(lessons.map((l) => l.code));
    for (const code of PUBLISHED_NEW_LESSON_CODES) {
      expect(codes.has(code), `${code}가 /v1/learning/paths에 없음`).toBe(true);
    }
    for (const code of ["lesson-01", "lesson-02", "lesson-03", "lesson-04", "lesson-05"]) {
      expect(codes.has(code), `${code}가 /v1/learning/paths에 없음`).toBe(true);
    }
  });
});

test.describe("데스크톱 1280x900 — 게시된 lesson-06~15", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("/learn 목록: 15개 전체 공개, lesson-06~15 제목·순서 정확, 중복 없음, 카드 클릭 시 상세로 이동", async ({
    page,
    request,
  }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("desktop-list"));

    const lessons = flattenLessons(await fetchLearningPaths(request));
    const coreLessons = lessons.filter((l) => /^lesson-\d{2}$/.test(l.code));
    expect(new Set(coreLessons.map((l) => l.code)).size).toBe(coreLessons.length); // 중복 코드 없음
    expect(coreLessons).toHaveLength(15); // lesson-01~15

    const newLessons = coreLessons.filter((l) =>
      (PUBLISHED_NEW_LESSON_CODES as readonly string[]).includes(l.code)
    );
    expect(newLessons).toHaveLength(10);
    const byOrder = [...newLessons].sort((a, b) => a.order_index - b.order_index);
    expect(byOrder.map((l) => l.code)).toEqual([...PUBLISHED_NEW_LESSON_CODES]);
    for (const lesson of newLessons) {
      expect(lesson.title).toBe(PUBLISHED_NEW_LESSON_TITLES[lesson.code]);
    }

    await page.goto("/learn");
    for (const lesson of newLessons) {
      // 카드의 접근성 이름은 "{제목} {예상 분}분"이다(apps/web/src/app/(app)/learn/page.tsx).
      // 제목만으로 느슨하게 매칭하면 우연히 부분 문자열이 겹치는 다른 강의/챌린지 카드와
      // 충돌할 수 있어(예: "시장가와 지정가" vs "주문 방식: 시장가와 지정가") 정확히 매칭한다.
      const link = page.getByRole("link", { name: `${lesson.title} ${lesson.estimated_minutes}분`, exact: true });
      await expect(link, `${lesson.code}(${lesson.title}) 카드가 정확히 1개여야 함`).toHaveCount(1);
    }

    const firstNew = newLessons[0];
    await page
      .getByRole("link", { name: `${firstNew.title} ${firstNew.estimated_minutes}분`, exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: firstNew.title, exact: true })).toBeVisible();
  });

  test("lesson-06~15 상세: 200 응답, 핵심 블록 표시, 출처 영역, 퀴즈 4문항, 채점 전 정답 정보 비노출", async ({
    page,
    request,
  }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("desktop-detail"));

    const lessons = flattenLessons(await fetchLearningPaths(request)).filter((l) =>
      (PUBLISHED_NEW_LESSON_CODES as readonly string[]).includes(l.code)
    );
    expect(lessons).toHaveLength(10);

    for (const lesson of lessons) {
      const response = await page.goto(`/learn/${lesson.id}`);
      expect(response?.status(), `${lesson.code} 상세 페이지 HTTP 상태`).toBe(200);
      await expect(page.getByRole("heading", { level: 1, name: lesson.title, exact: true })).toBeVisible();

      for (const label of ["핵심 요약", "흔한 오해", "관련 용어", "관련 실습"]) {
        await expect(
          page.getByRole("heading", { level: 2, name: label }),
          `${lesson.code}에 "${label}" 블록이 있어야 함`
        ).toBeVisible();
      }

      const sourceParagraph = page.locator("p", { hasText: "출처:" });
      await expect(sourceParagraph, `${lesson.code} 출처 영역`).toHaveCount(1);
      if (lesson.code === LESSON_CODE_WITHOUT_SOURCE_URL) {
        // source_url이 없어도 화면이 에러 없이 렌더된다 — 링크 없이 텍스트만 표시.
        await expect(sourceParagraph.locator("a")).toHaveCount(0);
      } else {
        await expect(sourceParagraph.locator("a"), `${lesson.code}는 출처 링크가 있어야 함`).toHaveCount(1);
      }

      await expect(page.getByText(/문항\s*4개/), `${lesson.code} 퀴즈 문항 수 표시`).toBeVisible();

      // 채점 전 사전 조회 API 레벨에서 is_correct/explanation이 전혀 내려오지 않는지 확인
      // (page.request는 로그인된 브라우저 컨텍스트의 쿠키를 그대로 공유한다).
      const detailRes = await page.request.get(`${STAGING_API_BASE_URL}/v1/lessons/${lesson.id}`);
      expect(detailRes.ok(), `${lesson.code} GET /v1/lessons/{id}`).toBe(true);
      const detail = await detailRes.json();
      expect(detail.quiz).toBeTruthy();

      const quizRes = await page.request.get(`${STAGING_API_BASE_URL}/v1/quizzes/${detail.quiz.id}`);
      expect(quizRes.ok(), `${lesson.code} GET /v1/quizzes/{id}`).toBe(true);
      const quizBodyText = await quizRes.text();
      expect(quizBodyText, `${lesson.code} 퀴즈 사전 조회 응답에 is_correct 노출됨`).not.toContain("is_correct");
      expect(quizBodyText, `${lesson.code} 퀴즈 사전 조회 응답에 explanation 노출됨`).not.toContain("explanation");
      const quizBody = JSON.parse(quizBodyText);
      expect(quizBody.questions, `${lesson.code} 퀴즈 문항 수`).toHaveLength(4);
      for (const q of quizBody.questions) {
        expect(q.choices.length, `${lesson.code} 문항 선택지 수`).toBeGreaterThanOrEqual(2);
      }
    }
  });

  test("퀴즈 진행(lesson-06): 선택지 표시 순서 유지, 채점 후 정답·오답 해설이 올바른 문항에 표시", async ({
    page,
    request,
  }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("desktop-quiz-flow"));
    const lessons = flattenLessons(await fetchLearningPaths(request));
    const target = lessons.find((l) => l.code === "lesson-06");
    expect(target, "lesson-06을 찾을 수 없음").toBeTruthy();

    await page.goto(`/learn/${target!.id}`);
    await page.getByRole("button", { name: "퀴즈 풀기" }).click();

    const radioLabels = page.locator("label:has(input[type='radio'])");
    await expect(radioLabels).toHaveCount(16); // 4문항 x 4선택지

    // 채점 전에는 정답 표시가 전혀 없어야 한다.
    await expect(page.getByText("(정답)")).toHaveCount(0);

    const orderBeforeSelect = await radioLabels.allTextContents();

    // 문항(name=q-{questionId})별로 첫 선택지를 고른다 — 정답 여부와 무관하게
    // "선택지 순서 유지"와 "피드백이 올바른 문항에 귀속되는지"만 검증하면 된다.
    const radios = page.locator("input[type='radio']");
    const radioCount = await radios.count();
    const seenGroups = new Set<string>();
    for (let i = 0; i < radioCount; i++) {
      const name = await radios.nth(i).getAttribute("name");
      if (name && !seenGroups.has(name)) {
        await radios.nth(i).check();
        seenGroups.add(name);
      }
    }
    expect(seenGroups.size).toBe(4);

    const orderAfterSelect = await radioLabels.allTextContents();
    expect(orderAfterSelect).toEqual(orderBeforeSelect);

    await page.getByRole("button", { name: "제출하기" }).click();
    await expect(page.getByText(/점수\s*\d+%\s*·\s*(합격|미합격)/)).toBeVisible();

    // 문항별 채점 결과는 "{n}. {prompt} — 정답/오답" 문단으로 표시된다. 이 문단을 감싸는
    // .card는 퀴즈 섹션 전체를 감싸는 바깥 .card(stack)와도 CSS 클래스가 겹치므로,
    // "가장 가까운 부모" 기준으로 직접 탐색해 바깥 컨테이너까지 잘못 세지 않게 한다.
    const resultParagraphs = page.locator("p", { hasText: /—\s*(정답|오답)$/ });
    await expect(resultParagraphs, "채점 결과 문단은 문항 수(4)만큼 있어야 함").toHaveCount(4);
    for (let i = 0; i < 4; i++) {
      const questionCard = resultParagraphs.nth(i).locator("xpath=..");
      // 문항마다 "정답"으로 표시된 선택지가 정확히 하나 — 즉 정답 라벨이 엉뚱한 문항에 붙지 않는다.
      await expect(questionCard.locator("li", { hasText: "(정답)" })).toHaveCount(1);
    }
  });
});

test.describe("모바일 390x844 — 게시된 lesson-06~15", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("/learn 및 lesson-06~15 상세: 가로 스크롤 없음, 핵심 요소 잘림 없음", async ({ page, request }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("mobile-layout"));

    const lessons = flattenLessons(await fetchLearningPaths(request)).filter((l) =>
      (PUBLISHED_NEW_LESSON_CODES as readonly string[]).includes(l.code)
    );

    await page.goto("/learn");
    // 목록이 실제로 렌더링된 뒤(로딩/세션 확인 상태가 아닌)에 오버플로를 측정한다 —
    // 그렇지 않으면 과도기적 로딩 화면의 레이아웃을 잘못 검사할 수 있다.
    for (const lesson of lessons) {
      // 정확한 접근성 이름("{제목} {분}분")으로 매칭한다 — 제목만으로는 다른 강의/챌린지
      // 카드와 부분 문자열이 겹칠 수 있다(데스크톱 목록 테스트와 동일한 이유).
      await expect(
        page.getByRole("link", { name: `${lesson.title} ${lesson.estimated_minutes}분`, exact: true })
      ).toBeVisible();
    }
    await assertNoHorizontalOverflow(page);

    for (const lesson of lessons) {
      await page.goto(`/learn/${lesson.id}`);
      const heading = page.getByRole("heading", { level: 1, name: lesson.title, exact: true });
      await expect(heading).toBeVisible();
      // 본문이 실제로 렌더링된 뒤에 오버플로를 측정한다(로딩/세션 확인 상태 배제).
      await assertNoHorizontalOverflow(page);
      const box = await heading.boundingBox();
      expect(box, `${lesson.code} 제목 영역`).toBeTruthy();
      expect(box!.width).toBeLessThanOrEqual(390);

      const completeButton = page.getByRole("button", { name: /학습 완료로 표시|이미 완료한 강의입니다/ }).first();
      await expect(completeButton.or(page.getByText("이미 완료한 강의입니다."))).toBeVisible();
    }
  });

  test("퀴즈(lesson-06): 선택·제출 가능, 결과는 텍스트로도 전달됨, 출처 링크가 화면 밖으로 넘치지 않음, 선택지 터치 영역이 겹치지 않음", async ({
    page,
    request,
  }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("mobile-quiz"));
    const lessons = flattenLessons(await fetchLearningPaths(request));
    const target = lessons.find((l) => l.code === "lesson-06");
    expect(target).toBeTruthy();

    await page.goto(`/learn/${target!.id}`);
    await expect(page.getByRole("heading", { level: 1, name: target!.title, exact: true })).toBeVisible();
    // 본문이 실제로 렌더링된 뒤에 오버플로를 측정한다(로딩/세션 확인 상태 배제).
    await assertNoHorizontalOverflow(page);

    // 긴 출처 URL(krx.co.kr 전체 경로)이 뷰포트 밖으로 넘치지 않는지 확인.
    const sourceLink = page.locator("p", { hasText: "출처:" }).locator("a");
    await expect(sourceLink).toBeVisible();
    const sourceBox = await sourceLink.boundingBox();
    expect(sourceBox).toBeTruthy();
    expect(sourceBox!.x + sourceBox!.width).toBeLessThanOrEqual(390 + 1);

    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    const radioLabels = page.locator("label:has(input[type='radio'])");
    await expect(radioLabels).toHaveCount(16);

    // 터치 대상(각 선택지 라벨)이 세로로 서로 겹치지 않는지 확인.
    const boxes = [];
    for (let i = 0; i < 16; i++) {
      const b = await radioLabels.nth(i).boundingBox();
      expect(b, `선택지 ${i} bounding box`).toBeTruthy();
      boxes.push(b!);
    }
    for (let i = 0; i < boxes.length - 1; i++) {
      expect(boxes[i].y + boxes[i].height, `선택지 ${i}와 ${i + 1}이 겹치면 안 됨`).toBeLessThanOrEqual(
        boxes[i + 1].y + 1
      );
    }

    const radios = page.locator("input[type='radio']");
    const radioCount = await radios.count();
    const seenGroups = new Set<string>();
    for (let i = 0; i < radioCount; i++) {
      const name = await radios.nth(i).getAttribute("name");
      if (name && !seenGroups.has(name)) {
        await radios.nth(i).check();
        seenGroups.add(name);
      }
    }
    await page.getByRole("button", { name: "제출하기" }).click();

    // 합격/미합격 여부가 색상뿐 아니라 텍스트로도 전달되는지 확인.
    const resultBanner = page.getByText(/점수\s*\d+%\s*·\s*(합격|미합격)/);
    await expect(resultBanner).toBeVisible();
    await expect(resultBanner).toHaveText(/합격|미합격/);
    await assertNoHorizontalOverflow(page);
  });
});

test.describe("금지 문구·필수 고지 검사 — lesson-06~15", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("과장·확정적 투자 권유 문구가 없고, lesson-09에는 교육용 가정치·세무자문 아님 고지가 표시된다", async ({
    page,
    request,
  }) => {
    await signUpStagingTestUser(page, uniqueStagingEmail("phrase-scan"));
    const lessons = flattenLessons(await fetchLearningPaths(request)).filter((l) =>
      (PUBLISHED_NEW_LESSON_CODES as readonly string[]).includes(l.code)
    );

    for (const lesson of lessons) {
      await page.goto(`/learn/${lesson.id}`);
      // 클라이언트 세션 확인("세션을 확인하는 중입니다...")이 끝나고 실제 본문이
      // 렌더링될 때까지 기다린 뒤에 텍스트를 캡처한다 — 그렇지 않으면 로딩 문구만
      // 캡처돼 문구 검사가 무의미해진다.
      await expect(page.getByRole("heading", { level: 1, name: lesson.title, exact: true })).toBeVisible();
      const bodyText = await page.locator("body").innerText();

      for (const { label, pattern } of FORBIDDEN_INVESTMENT_PHRASES) {
        expect(pattern.test(bodyText), `${lesson.code} 화면에서 금지 문구(${label}) 발견됨`).toBe(false);
      }

      if (lesson.code === "lesson-09") {
        expect(bodyText, "lesson-09에 '가정치' 고지가 있어야 함").toContain("가정치");
        expect(bodyText, "lesson-09에 세무 자문 아님 고지가 있어야 함").toContain("세무 자문");
      }
    }
  });
});

test.describe("콘텐츠 블록 라벨 참고", () => {
  test("BLOCK_LABEL 매핑에 이 스펙이 검증하는 모든 라벨이 포함돼 있다(회귀 방지용 자체 점검)", async () => {
    for (const label of ["핵심 요약", "흔한 오해", "관련 용어", "관련 실습"]) {
      expect(Object.values(CONTENT_BLOCK_LABELS)).toContain(label);
    }
  });
});
