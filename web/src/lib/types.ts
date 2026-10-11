export type Mode = "live" | "replay";

export interface AppStateInfo {
  mode: Mode;
  mode_reason: string;
  model: string;
  today: string;
  household: string;
  synthetic: boolean;
  suggestions: string[];
}

export interface Account {
  id: string;
  name: string;
  type: string;
  balance: number;
  floor: number;
}

export interface ForecastEvent {
  label: string;
  account: string;
  amount: number;
  kind: "recurring" | "scheduled" | "proposed";
}

export interface ForecastDay {
  date: string;
  day: string;
  checking: number;
  savings: number;
  events: ForecastEvent[];
}

export interface Alert {
  kind: "overdraft" | "tight";
  low: number;
  low_date: string;
  low_day: string;
  first_below_zero?: string;
  first_below_zero_day?: string;
  before_payday?: boolean;
}

export interface Recurring {
  id: string;
  name: string;
  kind: string;
  cadence: string;
  amount: number;
  previous: number | null;
  price_changed: boolean;
  next_date: string;
  status: string;
}

export interface Home {
  today: string;
  household: string;
  accounts: Account[];
  floors: Record<string, number>;
  next_payday: string | null;
  next_payday_day: string | null;
  next_pay: number | null;
  avg_daily_spend: number;
  low: { amount: number; date: string; day: string };
  alert: Alert | null;
  forecast: ForecastDay[];
  recurring: Recurring[];
  scheduled: { entry_id: number; date: string; label: string; amount: number; from: string; to: string }[];
}

export interface Txn {
  id: number;
  posting_id: number;
  date: string;
  day: string;
  account: string;
  amount: number;
  merchant: string;
  memo: string;
  category: string;
  kind: string;
  source: string;
  status: string;
}

export interface Step {
  seq: number;
  type: string;
  name: string;
  data: Record<string, any>;
  ms: number | null;
  at: string;
}

export interface PolicyCheck {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface LowPair {
  before: { usd: number; date: string; day: string };
  after: { usd: number; date: string; day: string };
}

export interface Approval {
  id: string;
  run_id: string;
  tool: "move_money" | "cancel_subscription";
  args: Record<string, any>;
  preview: {
    kind: "transfer" | "cancel";
    amount_usd?: number;
    date?: string;
    day?: string;
    when?: string;
    from?: { id: string; name: string };
    to?: { id: string; name: string };
    memo?: string;
    low_points?: Record<string, LowPair>;
    name?: string;
    previous_amount_usd?: number | null;
    next_charge?: string;
    saves_next_30_days_usd?: number;
    checks: PolicyCheck[];
  };
  status: "pending" | "approved" | "declined" | "expired";
  created_at: string;
  waiting?: boolean;
}

export interface RunSummary {
  id: string;
  kind: "chat" | "eval";
  prompt: string;
  provider: Mode;
  model: string;
  status: "running" | "done" | "error";
  started_at: string;
  duration_ms: number | null;
  num_turns: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_creation_tokens: number | null;
  cache_read_tokens: number | null;
  cost_usd: number | null;
  final_text: string;
  grounded: boolean | null;
  ungrounded: string[];
  error: string | null;
  case_id: string | null;
  eval_run_id: string | null;
  steps: number | null;
}

export interface RunDetail extends RunSummary {
  trace: Step[];
}

export interface ChatRun extends RunSummary {
  gate_steps: Step[];
  approvals: Approval[];
}

export interface EvalCheck {
  id: string;
  label: string;
  passed: boolean | null;
  detail: string;
}

export interface EvalCase {
  id: string;
  title: string;
  prompt: string;
  approver: string;
  status: "queued" | "running" | "passed" | "failed" | "error";
  checks: EvalCheck[];
  error: string | null;
  run: RunSummary | null;
}

export interface EvalRun {
  id: string;
  provider: Mode;
  model: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  cases: EvalCase[];
  summary: { cases: number; finished: number; passed: number; checks: number; checks_passed: number };
}

export type StreamEvent =
  | { type: "step"; step: Step }
  | { type: "approval_request"; approval: Approval }
  | { type: "approval_resolved"; approval_id: string; decision: string }
  | { type: "run_started"; run_id: string; provider: Mode; model: string }
  | { type: "run_finished"; run_id: string; status: string; final_text: string }
  | { type: "money_changed" };
