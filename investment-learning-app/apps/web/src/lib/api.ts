import type {
  BarResponse,
  BiasReportResponse,
  InstrumentDetail,
  InstrumentSummary,
  JournalCoachingResponse,
  JournalResponse,
  LearningPathResponse,
  LearningSummaryResponse,
  LessonDetailResponse,
  LessonProgressResponse,
  OrderPreviewResponse,
  OrderResponse,
  PerformanceResponse,
  PortfolioResponse,
  PositionResponse,
  QuizAttemptResponse,
  QuizDetailResponse,
  UserResponse,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// 2026-08: access/refresh 토큰을 localStorage가 아니라 서버가 관리하는 HttpOnly
// Secure 쿠키로 옮겼다 — JS가 토큰 문자열을 절대 읽거나 다루지 않는다. 이제
// 인증은 매 요청에 credentials: "include"로 쿠키를 실어 보내는 것으로 끝난다.

/** 인증이 완전히 실패(refresh까지 실패)했을 때 앱에 알리는 훅. AuthProvider가
 * 등록해서 전역 로그인 상태를 "미인증"으로 내리고 로그인 화면으로 보낸다. */
let onAuthFailure: (() => void) | null = null;
export function setAuthFailureHandler(handler: (() => void) | null) {
  onAuthFailure = handler;
}

// --- 레거시 localStorage 토큰 정리 (마이그레이션 shim) ---
// TODO(cookie-auth-migration): 예전 버전이 localStorage에 남겨둔 access/refresh
// token을 지운다. 값을 읽지도, 서버로 보내지도, 로그로 남기지도 않는다 — 존재
// 여부만 보고 즉시 삭제한다. refresh token 최대 수명(기본 30일)이 지나 예전
// 세션이 전부 만료된 뒤에는 이 함수와 호출부를 통째로 지워도 안전하다.
const LEGACY_LOCALSTORAGE_TOKEN_KEYS = ["ilapp_access_token", "ilapp_refresh_token"];
export function purgeLegacyLocalStorageTokens(): void {
  if (typeof window === "undefined") return;
  for (const key of LEGACY_LOCALSTORAGE_TOKEN_KEYS) {
    window.localStorage.removeItem(key);
  }
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(", ");
    }
    return `요청이 실패했습니다 (${res.status})`;
  } catch {
    return `요청이 실패했습니다 (${res.status})`;
  }
}

// 여러 요청이 동시에 401을 받아도 /v1/auth/refresh 호출은 한 번만 나가도록
// 진행 중인 refresh Promise를 공유한다(single-flight).
let refreshInFlight: Promise<boolean> | null = null;

function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  idempotencyKey?: string;
}

async function request<T>(path: string, options: RequestOptions = {}, _retried = false): Promise<T> {
  const { method = "GET", body, auth = true, idempotencyKey } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      credentials: "include", // 인증 쿠키를 실어 보낸다. Authorization 헤더는 더 이상 쓰지 않는다.
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.");
  }

  if (res.status === 401 && auth && !_retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, options, true);
    // refresh까지 실패했다 — 무한 재시도하지 않고 앱에 로그아웃을 알린 뒤 에러로 종료한다.
    onAuthFailure?.();
  }

  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Auth ---
export function signup(payload: {
  email: string;
  password: string;
  birth_date: string;
  consents: { consent_type: "TERMS" | "PRIVACY" | "MARKETING"; version: string; agreed: boolean }[];
}) {
  return request<UserResponse>("/v1/auth/signup", { method: "POST", body: payload, auth: false });
}

export function login(payload: { email: string; password: string }) {
  return request<UserResponse>("/v1/auth/login", { method: "POST", body: payload, auth: false });
}

/** 현재 인증 상태 확인용. 실패(401)하면 로그인되어 있지 않은 것이다. */
export const getMe = () => request<UserResponse>("/v1/auth/me");

export function logout(): Promise<void> {
  return request<void>("/v1/auth/logout", { method: "POST" });
}

// --- Learning ---
export const getLearningPaths = () => request<LearningPathResponse[]>("/v1/learning/paths");
export const getLesson = (lessonId: string) => request<LessonDetailResponse>(`/v1/lessons/${lessonId}`);
export const getQuiz = (quizId: string) => request<QuizDetailResponse>(`/v1/quizzes/${quizId}`);
export const updateLessonProgress = (lessonId: string, status: "IN_PROGRESS" | "COMPLETED") =>
  request<LessonProgressResponse & { xp_awarded: number }>(`/v1/lessons/${lessonId}/progress`, {
    method: "POST",
    body: { status },
  });
export const submitQuizAttempt = (quizId: string, answers: Record<string, string[]>) =>
  request<QuizAttemptResponse>(`/v1/quizzes/${quizId}/attempts`, { method: "POST", body: { answers } });
export const getLearningSummary = () => request<LearningSummaryResponse>("/v1/me/learning-summary");

// --- Instruments ---
export const searchInstruments = (q: string) =>
  request<InstrumentSummary[]>(`/v1/instruments/search?q=${encodeURIComponent(q)}`);
export const getInstrument = (instrumentId: string) =>
  request<InstrumentDetail>(`/v1/instruments/${instrumentId}`);
export const getInstrumentBars = (instrumentId: string) =>
  request<BarResponse[]>(`/v1/instruments/${instrumentId}/bars`);

// --- Portfolio ---
export const getMyPortfolio = () => request<PortfolioResponse>("/v1/me/portfolio");
export const getPositions = (portfolioId: string) =>
  request<PositionResponse[]>(`/v1/portfolios/${portfolioId}/positions`);
export const getPerformance = (portfolioId: string) =>
  request<PerformanceResponse>(`/v1/portfolios/${portfolioId}/performance`);

// --- Orders ---
export const previewOrder = (
  portfolioId: string,
  payload: { instrument_id: string; side: "BUY" | "SELL"; order_type: "MARKET" | "LIMIT"; quantity: string }
) => request<OrderPreviewResponse>(`/v1/portfolios/${portfolioId}/orders/preview`, { method: "POST", body: payload });

export const createOrder = (
  portfolioId: string,
  payload: {
    instrument_id: string;
    side: "BUY" | "SELL";
    order_type: "MARKET" | "LIMIT";
    quantity: string;
    pre_trade_journal_id?: string;
  },
  idempotencyKey: string
) =>
  request<OrderResponse>(`/v1/portfolios/${portfolioId}/orders`, {
    method: "POST",
    body: payload,
    idempotencyKey,
  });

// --- Journals ---
export const createPreTradeJournal = (payload: {
  portfolio_id: string;
  instrument_id: string;
  thesis: string;
  supporting_evidence: string[];
  counter_evidence: string[];
  expected_holding_period?: string;
  entry_condition?: string;
  target_condition?: string;
  stop_loss_condition?: string;
  planned_weight_pct?: string;
  confidence_level?: number;
}) => request<JournalResponse>("/v1/journals/pre-trade", { method: "POST", body: payload });

export const getJournal = (journalId: string) => request<JournalResponse>(`/v1/journals/${journalId}`);
export const listMyJournals = () => request<JournalResponse[]>("/v1/me/journals");

export const submitPostTradeReview = (
  journalId: string,
  payload: {
    followed_plan: boolean;
    expectation_gap?: string;
    behavior_to_repeat?: string;
    behavior_to_change?: string;
    emotion_tags?: string[];
  }
) => request<JournalResponse>(`/v1/journals/${journalId}/post-trade`, { method: "POST", body: payload });

export const getJournalCoaching = (journalId: string) =>
  request<JournalCoachingResponse>(`/v1/journals/${journalId}/coaching`);

export const getBiasReport = () => request<BiasReportResponse>("/v1/me/bias-report");
