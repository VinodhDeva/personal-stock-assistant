import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, del, post } from "../services/api";
import type {
  AppSettings,
  Backtest,
  History,
  Indicators,
  Page,
  PaperTrade,
  Portfolio,
  PriceAlert,
  ProviderStatus,
  Quote,
  Signal,
  WatchlistItem,
} from "../types/api";

// Polling a free provider faster than it updates does not make data fresher; 60s is plenty.
const QUOTE_REFRESH_MS = 60_000;

export const useWatchlist = () => useQuery({ queryKey: ["watchlist"], queryFn: () => api<WatchlistItem[]>("/api/watchlist") });

export const useQuote = (symbol: string) =>
  useQuery({
    queryKey: ["quote", symbol],
    queryFn: () => api<Quote>(`/api/stocks/${encodeURIComponent(symbol)}/quote`),
    refetchInterval: QUOTE_REFRESH_MS,
  });

export const useHistory = (symbol: string, period: string) =>
  useQuery({
    queryKey: ["history", symbol, period],
    queryFn: () => api<History>(`/api/stocks/${encodeURIComponent(symbol)}/history?period=${period}`),
  });

export const useIndicators = (symbol: string, period: string) =>
  useQuery({
    queryKey: ["indicators", symbol, period],
    queryFn: () => api<Indicators>(`/api/stocks/${encodeURIComponent(symbol)}/indicators?period=${period}`),
  });

export const useLatestSignals = () =>
  useQuery({ queryKey: ["signals", "latest"], queryFn: () => api<Signal[]>("/api/signals/latest") });

export const useSignals = (symbol?: string, limit = 20) =>
  useQuery({
    queryKey: ["signals", symbol ?? "all", limit],
    queryFn: () =>
      api<Page<Signal>>(symbol ? `/api/signals/${encodeURIComponent(symbol)}?limit=${limit}` : `/api/signals?limit=${limit}`),
  });

export const useProviders = () =>
  useQuery({ queryKey: ["providers"], queryFn: () => api<ProviderStatus>("/api/providers/status") });

export const usePortfolio = () => useQuery({ queryKey: ["portfolio"], queryFn: () => api<Portfolio>("/api/portfolio") });

export const useTrades = () =>
  useQuery({ queryKey: ["trades"], queryFn: () => api<Page<PaperTrade>>("/api/portfolio/trades?limit=100") });

export const useAlerts = (symbol?: string) =>
  useQuery({
    queryKey: ["alerts", symbol ?? "all"],
    queryFn: () => api<PriceAlert[]>(symbol ? `/api/alerts?symbol=${encodeURIComponent(symbol)}` : "/api/alerts"),
  });

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => api<AppSettings>("/api/settings") });

export const useBacktest = (symbol: string, enabled: boolean) =>
  useQuery({
    queryKey: ["backtest", symbol],
    queryFn: () => api<Backtest>(`/api/backtest/ema_crossover?symbol=${encodeURIComponent(symbol)}&period=2y`),
    enabled,
  });

export function useRefreshSignals() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post<Record<string, number>>("/api/signals/refresh"),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => del(`/api/watchlist/${encodeURIComponent(symbol)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}
