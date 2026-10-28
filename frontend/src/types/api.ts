export type Freshness = "live" | "delayed" | "cached" | "historical" | "stale";
export type SignalType = "BUY" | "SELL" | "HOLD";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface WatchlistItem {
  symbol: string;
  exchange: string;
  name: string | null;
  notify_signals: boolean;
  warning?: string | null;
}

export interface Quote {
  symbol: string;
  exchange: string;
  price: number;
  previous_close: number | null;
  change_pct: number | null;
  data_timestamp: string;
  fetched_at: string;
  provider: string;
  freshness: Freshness;
  warnings: string[];
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SeriesMeta {
  symbol: string;
  exchange: string;
  provider: string;
  interval: string;
  freshness: Freshness;
  data_timestamp: string | null;
  fetched_at: string;
  warnings: string[];
}

export interface History extends SeriesMeta {
  candles: Candle[];
}

export interface IndicatorPoint {
  time: number;
  close: number | null;
  rsi_14: number | null;
  sma_20: number | null;
  sma_50: number | null;
  ema_12: number | null;
  ema_26: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  avg_volume_20: number | null;
  atr_14: number | null;
  pct_change: number | null;
}

export interface Indicators extends SeriesMeta {
  latest: IndicatorPoint | null;
  series: IndicatorPoint[];
}

export interface Risk {
  stop_loss?: number | null;
  take_profit?: number | null;
  risk_per_share?: number | null;
  atr_14?: number | null;
}

export interface Signal {
  id: number;
  symbol: string;
  exchange: string;
  signal_type: SignalType;
  price: number | null;
  signal_timestamp: string;
  data_timestamp: string | null;
  freshness: Freshness;
  provider: string | null;
  indicators: Record<string, number | null>;
  rules_triggered: string[];
  rules_failed: string[];
  invalidation: string[];
  risk: Risk;
  strategy_version: string;
}

export interface PriceAlert {
  id: number;
  symbol: string;
  condition: "above" | "below";
  price: number;
  active: boolean;
  note: string | null;
  created_at: string;
  triggered_at: string | null;
  triggered_price: number | null;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number | null;
  market_value: number;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl: number | null;
  price_available: boolean;
  exposure_pct: number;
  price_meta?: { provider?: string; freshness?: Freshness; data_timestamp?: string; error?: string };
}

export interface Portfolio {
  starting_capital: number;
  cash: number;
  market_value: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_fees: number;
  exposure_pct: number;
  max_drawdown_pct: number;
  positions: Position[];
  simulated: boolean;
}

export interface PaperTrade {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  fees: number;
  stop_loss: number | null;
  take_profit: number | null;
  realized_pnl: number | null;
  reason: string | null;
  price_source: string | null;
  executed_at: string;
}

export interface ProviderStatus {
  providers: {
    name: string;
    configured: boolean;
    capabilities: Record<string, boolean | string>;
    last_error: string | null;
  }[];
  live_data_available: boolean;
  note: string;
  ollama: { reachable: boolean; model: string; model_available: boolean; installed_models?: string[] };
  telegram: { configured: boolean; help: string | null };
  scheduler: {
    enabled: boolean;
    market_timezone: string;
    market_open: string;
    market_close: string;
    last_run: { started_at: string | null; finished_at: string | null; result: Record<string, unknown> | null };
  };
}

export interface StrategyConfig {
  rsi_buy_min: number;
  rsi_buy_max: number;
  require_rsi_rising: boolean;
  require_close_above_sma20: boolean;
  volume_multiplier: number;
  atr_stop_multiplier: number;
  reward_risk_ratio: number;
  max_risk_per_trade_pct: number;
  max_portfolio_exposure_pct: number;
}

export interface AppSettings {
  strategy: StrategyConfig;
  strategy_schema: { properties: Record<string, { description?: string; title?: string }> };
  refresh_interval_seconds: number;
  stale_after_minutes: number;
  paper_starting_capital: number;
  notification_cooldown_minutes: number;
  ollama_model: string;
}

export interface ChatResponse {
  answer: string;
  llm_used: boolean;
  model?: string;
  llm_error?: string;
  refused?: boolean;
  deterministic_answer?: string;
  context: { as_of: string; signals: Signal[]; quotes: (Partial<Quote> & { symbol: string; error?: string })[] };
}

export interface Backtest {
  symbol: string;
  provider: string;
  freshness: Freshness;
  bars: number;
  start: string | null;
  end: string | null;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  buy_and_hold_return_pct: number | null;
  max_drawdown_pct: number;
  num_trades: number;
  win_rate_pct: number | null;
  total_costs: number;
  trades: {
    entry_time: string;
    entry_price: number;
    exit_time: string | null;
    exit_price: number | null;
    quantity: number;
    exit_reason: string | null;
    pnl: number | null;
  }[];
  assumptions: Record<string, string | number>;
}
