import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignalDetails } from "../src/components/SignalDetails";
import { StockDetailPage } from "../src/pages/StockDetailPage";
import { axeViolations, mockApi, renderAt } from "./helpers";
import { buySignal, holdSignal, quote } from "./fixtures";

describe("Signal details", () => {
  it("shows rules, timestamps, risk and invalidation", () => {
    renderAt(<SignalDetails signal={buySignal} />);
    const card = screen.getByRole("article", { name: "BUY signal for RELIANCE.NS" });
    expect(within(card).getByText("Potential BUY")).toBeInTheDocument();
    expect(within(card).getByText(/EMA12 crossed above EMA26/)).toBeInTheDocument();
    const risk = within(card).getByRole("region", { name: "Risk" });
    expect(risk).toHaveTextContent("Stop-loss ₹1,103.36");
    expect(risk).toHaveTextContent("Take-profit ₹1,267.28");
    expect(risk).toHaveTextContent("Invalidated if: EMA12 crosses back below EMA26");
    expect(card).toHaveTextContent("28 Oct 2026 (daily bar)");
    expect(card).toHaveTextContent("28 Oct 2026, 3:30 pm IST");
    expect(card).toHaveTextContent("ema_crossover_v1");
    expect(card).toHaveTextContent(/not investment advice/);
  });

  it("shows failed rules for HOLD", () => {
    renderAt(<SignalDetails signal={holdSignal} />);
    expect(screen.getByText("Not met / blocking")).toBeInTheDocument();
    expect(screen.getByText("RSI 38.0 outside [45, 70]")).toBeInTheDocument();
  });

  it("stock detail page renders charts, signals and is accessible", async () => {
    const candles = Array.from({ length: 5 }, (_, i) => ({ time: 1_760_000_000 + i * 86400, open: 1, high: 2, low: 1, close: 1.5, volume: 10 }));
    const meta = { symbol: "RELIANCE.NS", exchange: "NSE", provider: "yahoo", interval: "1d", freshness: "delayed", data_timestamp: "2026-10-27T18:30:00Z", fetched_at: "2026-10-28T10:00:00Z", warnings: [] };
    mockApi({
      "GET /api/stocks/RELIANCE.NS/quote": quote("RELIANCE.NS"),
      "GET /api/stocks/RELIANCE.NS/history": { ...meta, candles },
      "GET /api/stocks/RELIANCE.NS/indicators": { ...meta, latest: { time: 1, rsi_14: 55 }, series: [] },
      "GET /api/signals/RELIANCE.NS": { items: [buySignal], total: 1, limit: 10, offset: 0 },
      "GET /api/alerts": [],
    });
    const { container } = renderAt(<StockDetailPage />, "/stocks/RELIANCE.NS", "/stocks/:symbol");
    expect(await screen.findByRole("img", { name: /Candlestick price chart/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /RSI 14/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /MACD/ })).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: "BUY signal for RELIANCE.NS" })).toBeInTheDocument();
    expect(screen.getByText(/No alerts/)).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});
