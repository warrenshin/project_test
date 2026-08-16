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
  TokenResponse,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const ACCESS_TOKEN_KEY = "ilapp_access_token";
const REFRESH_TOKEN_KEY = "ilapp_refresh_token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getStoredTokens(): { accessToken: string | null; refreshToken: string | null } {
  if (typeof window === "undefined") return { accessToken: null, refreshToken: null };
  return {
    accessToken: window.localStorage.getItem(ACCESS_TOKEN_KEY),
    refreshToken: window.localStorage.getItem(REFRESH_TOKEN_KEY),
  };
}

export function storeTokens(tokens: TokenResponse) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
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

async function refreshAccessToken(): Promise<boolean> {
  const { refreshToken } = getStoredTokens();
  if (!refreshToken) return false;
  const res = await fetch(`${API_BASE_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    clearTokens();
    return false;
  }
  const tokens: TokenResponse = await res.json();
  storeTokens(tokens);
  return true;
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

  if (auth) {
    const { accessToken } = getStoredTokens();
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  }
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.");
  }

  if (res.status === 401 && auth && !_retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, options, true);
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
  return request<TokenResponse>("/v1/auth/signup", { method: "POST", body: payload, auth: false });
}

export function login(payload: { email: string; password: string }) {
  return request<TokenResponse>("/v1/auth/login", { method: "POST", body: payload, auth: false });
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
