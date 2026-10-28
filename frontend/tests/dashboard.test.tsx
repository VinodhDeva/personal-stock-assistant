import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardPage } from "../src/pages/DashboardPage";
import { axeViolations, mockApi, renderAt } from "./helpers";
import { buySignal, holdSignal, portfolio, providers, quote, watchlist } from "./fixtures";

const base = {
  "GET /api/watchlist": watchlist,
  "GET /api/signals/latest": [buySignal, holdSignal],
  "GET /api/providers/status": providers,
  "GET /api/portfolio": portfolio,
  "GET /api/stocks/RELIANCE.NS/quote": quote("RELIANCE.NS"),
  "GET /api/stocks/TCS.NS/quote": quote("TCS.NS", "stale"),
};

describe("Dashboard", () => {
  it("renders watchlist rows with prices, freshness and signals", async () => {
    mockApi(base);
    renderAt(<DashboardPage />);
    const row = (await screen.findByRole("link", { name: "RELIANCE.NS" })).closest("tr")!;
    expect(await within(row).findByText("₹1,158.00")).toBeInTheDocument();
    expect(within(row).getByText("-3.19%")).toBeInTheDocument();
    expect(within(row).getByText("Potential BUY")).toBeInTheDocument();
    expect(within(row).getByText("delayed")).toBeInTheDocument();
    const tcs = screen.getByRole("link", { name: "TCS.NS" }).closest("tr")!;
    expect(await within(tcs).findByText("stale")).toBeInTheDocument();
    expect(within(tcs).getByText("HOLD")).toBeInTheDocument();
    expect(await screen.findByText(/No configured free provider confirms real-time data/)).toBeInTheDocument();
    expect(screen.getByText("Equity").nextSibling).toHaveTextContent("₹10,00,000.00");
  });

  it("never labels delayed data as live", async () => {
    mockApi(base);
    renderAt(<DashboardPage />);
    await screen.findAllByText("delayed");
    expect(screen.queryByText(/^live$/i)).not.toBeInTheDocument();
  });

  it("shows loading then empty state", async () => {
    mockApi({ ...base, "GET /api/watchlist": [] });
    renderAt(<DashboardPage />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(await screen.findByText(/Your watchlist is empty/)).toBeInTheDocument();
  });

  it("shows an error state when the backend fails", async () => {
    mockApi({ ...base, "GET /api/watchlist": { __status: 500, error: { code: "x", message: "database down" } } });
    renderAt(<DashboardPage />);
    expect(await screen.findByText(/database down/)).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
  });

  it("shows a per-symbol error when a quote is unavailable", async () => {
    mockApi({
      ...base,
      "GET /api/stocks/TCS.NS/quote": { __status: 503, error: { code: "provider_unavailable", message: "yahoo: throttled" } },
    });
    renderAt(<DashboardPage />);
    expect(await screen.findByText(/Quote unavailable: yahoo: throttled/)).toBeInTheDocument();
  });

  it("has no detectable accessibility violations", async () => {
    mockApi(base);
    const { container } = renderAt(<DashboardPage />);
    await screen.findByText("Potential BUY");
    await screen.findAllByText("₹1,158.00");
    expect(await axeViolations(container)).toEqual([]);
  });
});
