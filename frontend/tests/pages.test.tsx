import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AssistantPage } from "../src/pages/AssistantPage";
import { PortfolioPage } from "../src/pages/PortfolioPage";
import { SettingsPage } from "../src/pages/SettingsPage";
import { axeViolations, mockApi, renderAt } from "./helpers";
import { portfolio, providers } from "./fixtures";

describe("other pages", () => {
  it("assistant shows deterministic fallback when Ollama is down", async () => {
    mockApi({
      "POST /api/assistant/chat": {
        answer: "RELIANCE.NS: latest signal HOLD",
        llm_used: false,
        llm_error: "Ollama unavailable (ConnectError)",
        context: { as_of: "2026-10-28T10:00:00Z", signals: [], quotes: [] },
      },
    });
    renderAt(<AssistantPage />);
    await userEvent.type(screen.getByLabelText("Your question"), "why hold?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("RELIANCE.NS: latest signal HOLD")).toBeInTheDocument();
    expect(screen.getByText(/Deterministic explanation \(Ollama unavailable/)).toBeInTheDocument();
  });

  it("portfolio rejects trades with the API reason", async () => {
    mockApi({
      "GET /api/portfolio": portfolio,
      "GET /api/portfolio/trades": { items: [], total: 0, limit: 100, offset: 0 },
      "POST /api/portfolio/paper-trades": { __status: 422, error: { code: "insufficient_cash", message: "needs 9,99,999.00" } },
    });
    renderAt(<PortfolioPage />);
    expect(await screen.findByText("No open simulated positions.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Symbol"), "INFY.NS");
    await userEvent.type(screen.getByLabelText("Quantity"), "999");
    await userEvent.click(screen.getByRole("button", { name: "Record paper trade" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs 9,99,999.00");
  });

  it("settings shows provider, Ollama and Telegram status and is accessible", async () => {
    mockApi({
      "GET /api/providers/status": providers,
      "GET /api/settings": {
        strategy: {
          rsi_buy_min: 45, rsi_buy_max: 70, require_rsi_rising: true, require_close_above_sma20: true,
          volume_multiplier: 1, atr_stop_multiplier: 2, reward_risk_ratio: 2, max_risk_per_trade_pct: 1,
          max_portfolio_exposure_pct: 60,
        },
        strategy_schema: { properties: {} },
        refresh_interval_seconds: 300,
        stale_after_minutes: 30,
        paper_starting_capital: 1_000_000,
        notification_cooldown_minutes: 60,
        ollama_model: "qwen3.5:9b",
      },
    });
    const { container } = renderAt(<SettingsPage />);
    expect(await screen.findByText(/Not reachable/)).toBeInTheDocument();
    expect(screen.getByText(/Set TELEGRAM_BOT_TOKEN/)).toBeInTheDocument();
    expect(await screen.findByLabelText("RSI minimum for BUY")).toHaveValue(45);
    expect(await axeViolations(container)).toEqual([]);
  });
});
