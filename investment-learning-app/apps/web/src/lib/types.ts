export interface UserResponse {
  id: string;
  email: string;
}

export interface LessonSummary {
  id: string;
  title: string;
  estimated_minutes: number;
  order_index: number;
}

export interface ModuleSummary {
  id: string;
  title: string;
  order_index: number;
  lessons: LessonSummary[];
}

export interface CourseSummary {
  id: string;
  title: string;
  description: string | null;
  order_index: number;
  modules: ModuleSummary[];
}

export interface LearningPathResponse {
  id: string;
  title: string;
  description: string | null;
  target_experience_level: string | null;
  courses: CourseSummary[];
}

export interface ContentBlockResponse {
  block_type: string;
  content: string;
  order_index: number;
}

export interface QuizSummary {
  id: string;
  title: string;
  question_count: number;
  pass_score_pct: number;
}

export interface LessonProgressResponse {
  status: string;
  completed_at: string | null;
}

export interface LessonDetailResponse {
  id: string;
  title: string;
  learning_objective: string | null;
  estimated_minutes: number;
  source: string | null;
  reviewed_by: string | null;
  content_blocks: ContentBlockResponse[];
  quiz: QuizSummary | null;
  progress: LessonProgressResponse | null;
}

export interface QuizChoice {
  id: string;
  label: string;
}

export interface QuizQuestion {
  id: string;
  prompt: string;
  question_type: string;
  choices: QuizChoice[];
}

export interface QuizDetailResponse {
  id: string;
  title: string;
  pass_score_pct: number;
  questions: QuizQuestion[];
}

export interface QuestionResult {
  question_id: string;
  correct: boolean;
  explanation: string | null;
}

export interface QuizAttemptResponse {
  score_pct: number;
  passed: boolean;
  xp_awarded: number;
  results: QuestionResult[];
}

export interface LearningSummaryResponse {
  total_xp: number;
  lessons_completed: number;
  quizzes_passed: number;
  current_streak_days: number;
  todays_xp: number;
  daily_xp_cap: number;
}

export interface InstrumentSummary {
  id: string;
  ticker: string;
  exchange: string;
  currency: string;
  name: string;
  industry: string | null;
}

export interface InstrumentDetail extends InstrumentSummary {
  is_tradable: boolean;
  last_price: string | null;
  price_as_of: string | null;
  price_source: string | null;
  delay_seconds: number | null;
}

export interface BarResponse {
  bar_start: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  source: string;
  as_of: string;
  delay_seconds: number;
}

// Phase A: 시장 데이터 신선도. UNAVAILABLE은 가격을 확인할 수 없다는 뜻이지
// 0원이라는 뜻이 아니다 — 관련 금액 필드는 항상 null로 함께 온다.
export type PriceStatus = "FRESH" | "STALE" | "UNAVAILABLE";
export type PortfolioMarketDataStatus = PriceStatus | "EMPTY";

export interface PortfolioResponse {
  id: string;
  base_currency: string;
  cash_balance: string;
  positions_market_value: string;
  total_assets: string;
  market_data_status: PortfolioMarketDataStatus;
  market_data_as_of: string | null;
  has_unavailable_positions: boolean;
  stale_position_count: number;
  unavailable_position_count: number;
}

export interface PositionResponse {
  instrument_id: string;
  ticker: string;
  quantity: string;
  average_cost: string;
  last_price: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  price_status: PriceStatus;
  price_as_of: string | null;
  price_source: string | null;
  price_age_seconds: number | null;
}

export interface PerformanceResponse {
  base_currency: string;
  cash_balance: string;
  positions_market_value: string;
  total_assets: string;
  total_deposited: string;
  simple_return_pct: string | null;
  realized_pnl: string;
  unrealized_pnl: string;
  total_commission: string;
  total_tax: string;
  market_data_status: PortfolioMarketDataStatus;
  market_data_as_of: string | null;
  has_unavailable_positions: boolean;
  stale_position_count: number;
  unavailable_position_count: number;
  performance_complete: boolean;
  note: string;
}

export interface OrderPreviewResponse {
  reference_price: string;
  estimated_fill_price: string;
  estimated_fillable: boolean;
  notional: string;
  commission: string;
  tax: string;
  fx_rate: string | null;
  estimated_cash_impact: string;
  currency: string;
  market_data_as_of: string;
  warnings: string[];
}

export interface OrderResponse {
  id: string;
  portfolio_id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT";
  quantity: string;
  limit_price: string | null;
  status: string;
  submitted_at: string;
  policy_version: string;
  warnings: string[];
}

export interface JournalResponse {
  id: string;
  portfolio_id: string;
  instrument_id: string;
  order_id: string | null;
  thesis: string | null;
  supporting_evidence: string[] | null;
  counter_evidence: string[] | null;
  expected_holding_period: string | null;
  entry_condition: string | null;
  target_condition: string | null;
  stop_loss_condition: string | null;
  planned_amount: string | null;
  planned_weight_pct: string | null;
  confidence_level: number | null;
  reference_links: string[] | null;
  market_data_snapshot: { close: string; as_of: string; source: string; delay_seconds: number } | null;
  actual_entry_at: string | null;
  actual_exit_at: string | null;
  followed_plan: boolean | null;
  expectation_gap: string | null;
  behavior_to_repeat: string | null;
  behavior_to_change: string | null;
  emotion_tags: string[] | null;
  process_score: string | null;
  process_score_breakdown: Record<string, number> | null;
}

export interface CoachingSource {
  type: string;
  id: string | null;
  title: string;
  as_of: string | null;
  source: string;
  delay_seconds: number | null;
}

export interface JournalCoachingResponse {
  process_score: string | null;
  process_score_breakdown: Record<string, number> | null;
  content: string;
  model: string;
  prompt_version: string;
  sources: CoachingSource[];
  degraded: boolean;
}

export interface BiasObservation {
  pattern: string;
  description: string;
  coaching_direction: string;
}

export interface BiasReportResponse {
  observations: BiasObservation[];
  note: string;
}

export interface ApiErrorBody {
  detail?: string | { msg: string }[];
}
