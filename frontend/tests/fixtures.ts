import type { Portfolio, ProviderStatus, Quote, Signal, WatchlistItem } from "../src/types/api";

export const watchlist: WatchlistItem[] = [
  { symbol: "RELIANCE.NS", exchange: "NSE", name: "Reliance Industries", notify_signals: true },
  { symbol: "TCS.NS", exchange: "NSE", name: "Tata Consultancy Services", notify_signals: false },
];

export const quote = (symbol: string, freshness: Quote["freshness"] = "delayed"): Quote => ({
  symbol,
  exchange: "NSE",
  price: 1158,
  previous_close: 1196.2,
  change_pct: -3.19,
  data_timestamp: "2026-10-28T09:58:00Z",
  fetched_at: "2026-10-28T10:00:00Z",
  provider: "yahoo",
  freshness,
  warnings: [],
});

export const buySignal: Signal = {
  id: 1,
  symbol: "RELIANCE.NS",
  exchange: "NSE",
  signal_type: "BUY",
  price: 1158,
  signal_timestamp: "2026-10-28T10:00:00Z",
  data_timestamp: "2026-10-27T18:30:00Z",
  freshness: "delayed",
  provider: "yahoo",
  indicators: { rsi_14: 55.2 },
  rules_triggered: ["EMA12 crossed above EMA26 on completed bar (EMA12 1190.19, EMA26 1188.44)", "RSI 55.2 within [45, 70]"],
  rules_failed: [],
  invalidation: ["EMA12 crosses back below EMA26", "close below stop-loss 1103.36"],
  risk: { stop_loss: 1103.36, take_profit: 1267.28, risk_per_share: 54.64, atr_14: 27.32 },
  strategy_version: "ema_crossover_v1",
};

export const holdSignal: Signal = {
  ...buySignal,
  id: 2,
  symbol: "TCS.NS",
  signal_type: "HOLD",
  rules_triggered: [],
  rules_failed: ["RSI 38.0 outside [45, 70]"],
  invalidation: [],
};

export const providers: ProviderStatus = {
  providers: [
    { name: "yahoo", configured: true, capabilities: { quotes: true, history: true, notes: "Unofficial" }, last_error: null },
    { name: "alpha_vantage", configured: false, capabilities: { quotes: true }, last_error: null },
  ],
  live_data_available: false,
  note: "No configured free provider confirms real-time data.",
  ollama: { reachable: false, model: "qwen3.5:9b", model_available: false },
  telegram: { configured: false, help: "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env and restart." },
  scheduler: {
    enabled: true,
    market_timezone: "Asia/Kolkata",
    market_open: "09:15:00",
    market_close: "15:30:00",
    last_run: { started_at: null, finished_at: null, result: null },
  },
};

export const portfolio: Portfolio = {
  starting_capital: 1_000_000,
  cash: 988_420,
  market_value: 11_580,
  equity: 1_000_000,
  realized_pnl: 0,
  unrealized_pnl: 0,
  total_fees: 0,
  exposure_pct: 1.16,
  max_drawdown_pct: 0,
  positions: [],
  simulated: true,
};
