import type { APIRequestContext, Page } from "@playwright/test";
import { STAGING_API_BASE_URL } from "../playwright.staging.config";

/** 실행마다 고유한 테스트 전용 이메일(UUID 기반). 기존 사용자/진도 데이터와 절대 겹치지 않는다. */
export function uniqueStagingEmail(tag: string): string {
  const uuid =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `staging-e2e-${tag}-${uuid}@example.com`;
}

export const STAGING_TEST_PASSWORD = "Staging-E2E-Test-Password-1!";

/** 신규 테스트 전용 계정으로 회원가입한다. 실제 사람이 화면을 조작하는 것과 동일한 경로
 * (폼 입력 → 제출)로만 진행한다 — API를 직접 호출해 우회하지 않는다. */
export async function signUpStagingTestUser(page: Page, email: string): Promise<void> {
  await page.goto("/signup");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호 (8자 이상)").fill(STAGING_TEST_PASSWORD);
  await page.getByLabel("생년월일").fill("2000-01-01");
  await page.getByLabel("(필수) 이용약관에 동의합니다").check();
  await page.getByLabel("(필수) 개인정보 처리방침에 동의합니다").check();
  await page.getByRole("button", { name: "가상자금으로 시작하기" }).click();
  await page.waitForURL("/");
}

export type LessonSummary = {
  id: string;
  code: string;
  title: string;
  estimated_minutes: number;
  order_index: number;
};

export type LearningPathsResponse = Array<{
  courses: Array<{
    modules: Array<{
      order_index: number;
      lessons: LessonSummary[];
    }>;
  }>;
}>;

/** GET /v1/learning/paths — 상태를 바꾸지 않는 안전한 조회이며 인증도 필요 없다
 * (CSRF Origin 검사는 GET/HEAD/OPTIONS에는 적용되지 않는다 — apps/api/app/core/csrf.py). */
export async function fetchLearningPaths(request: APIRequestContext): Promise<LearningPathsResponse> {
  const res = await request.get(`${STAGING_API_BASE_URL}/v1/learning/paths`);
  if (!res.ok()) {
    throw new Error(`GET /v1/learning/paths 실패: HTTP ${res.status()}`);
  }
  return res.json();
}

/** 응답을 code -> LessonSummary 맵으로 펼친다(모든 module.lessons를 순서 그대로 보존). */
export function flattenLessons(paths: LearningPathsResponse): LessonSummary[] {
  const out: LessonSummary[] = [];
  for (const path of paths) {
    for (const course of path.courses) {
      for (const mod of course.modules) {
        for (const lesson of mod.lessons) out.push(lesson);
      }
    }
  }
  return out;
}

/** lesson-06 ~ lesson-15, 실제 제목·순서(order_index)는 로컬 스테이징 DB에서 직접 확인한 값이다
 * (scripts/publish_reviewed_lessons_staging.sh로 게시된 콘텐츠 기준). */
export const PUBLISHED_NEW_LESSON_CODES = [
  "lesson-06",
  "lesson-07",
  "lesson-08",
  "lesson-09",
  "lesson-10",
  "lesson-11",
  "lesson-12",
  "lesson-13",
  "lesson-14",
  "lesson-15",
] as const;

export const PUBLISHED_NEW_LESSON_TITLES: Record<string, string> = {
  "lesson-06": "거래소와 장 운영시간",
  "lesson-07": "시장가와 지정가",
  "lesson-08": "호가·스프레드·유동성",
  "lesson-09": "수수료·세금·환율",
  "lesson-10": "투자수익률 계산",
  "lesson-11": "복리의 효과와 한계",
  "lesson-12": "변동성과 최대낙폭",
  "lesson-13": "분산투자의 원리",
  "lesson-14": "자산배분 기초",
  "lesson-15": "시가총액과 기업가치",
};

/** lesson-12만 source_url이 없다(REVIEW_REQUIRED 당시 원문 후보를 찾지 못한 강의) — 나머지 9개는 있다. */
export const LESSON_CODE_WITHOUT_SOURCE_URL = "lesson-12";

export const CONTENT_BLOCK_LABELS: Record<string, string> = {
  OBJECTIVE: "학습 목표",
  BODY: "본문",
  EXAMPLE: "예시",
  MISCONCEPTION: "흔한 오해",
  SUMMARY: "핵심 요약",
  SELF_CHECK: "스스로 확인하기",
  TERMS: "관련 용어",
  PRACTICE: "관련 실습",
  SOURCE: "출처",
};

/** 확정적·과장된 투자 권유 표현. 정상적인 교육용 문구(예: "체결이 보장되지 않을 수 있습니다",
 * "확정된 손익" 같은 중립적 용어)는 걸리지 않도록 구체적인 문구 단위로만 검사한다. */
export const FORBIDDEN_INVESTMENT_PHRASES: Array<{ label: string; pattern: RegExp }> = [
  { label: "수익 보장 표현", pattern: /(수익|원금)\s*(률)?\s*보장/ },
  { label: "무조건 수익 표현", pattern: /무조건\s*수익/ },
  { label: "확정적 상승 표현", pattern: /반드시\s*오른다|틀림없이\s*오릅니다|무조건\s*오릅니다/ },
  { label: "특정 종목 매수 지시", pattern: /지금\s*(매수|사세요)|매수(하세요|하십시오|해야\s*합니다)/ },
  { label: "특정 종목 매도 지시", pattern: /지금\s*매도|매도(하세요|하십시오|해야\s*합니다)/ },
  { label: "세율 단정 표현", pattern: /실제\s*세율은\s*\d/ },
  { label: "투자 성향/결과 진단 표현", pattern: /(투자\s*성향|포트폴리오|투자\s*결과)을?를?\s*진단(합니다|해드립니다|해준다)/ },
];

/** RegExp 리터럴에 안전하게 넣기 위한 이스케이프(제목 등 사용자 노출 문자열을 정규식으로 매칭할 때 사용). */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** 문서 전체 폭이 뷰포트를 넘어 가로 스크롤이 생기지 않는지 확인한다(모바일 반응형 검증용). */
export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
  );
  if (hasOverflow) {
    throw new Error(`페이지(${page.url()})에 가로 스크롤을 유발하는 콘텐츠 오버플로가 있습니다.`);
  }
}
