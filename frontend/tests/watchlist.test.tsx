import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WatchlistPage } from "../src/pages/WatchlistPage";
import { axeViolations, mockApi, renderAt } from "./helpers";
import { watchlist } from "./fixtures";

describe("Watchlist", () => {
  it("adds a symbol with the chosen exchange", async () => {
    let list = [...watchlist];
    const calls = mockApi({
      "GET /api/watchlist": () => list,
      "POST /api/watchlist": (_u: string, init?: RequestInit) => {
        const body = JSON.parse(String(init!.body));
        list = [...list, { symbol: "INFY.BO", exchange: "BSE", name: "Infosys", notify_signals: true }];
        return { ...body, symbol: "INFY.BO", exchange: "BSE", name: "Infosys", notify_signals: true, warning: null };
      },
    });
    renderAt(<WatchlistPage />);
    await screen.findByText("RELIANCE.NS");
    await userEvent.type(screen.getByLabelText("Symbol"), "infy");
    await userEvent.selectOptions(screen.getByLabelText("Exchange"), "BSE");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("INFY.BO")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ symbol: "infy", exchange: "BSE" });
  });

  it("shows validation errors from the API", async () => {
    mockApi({
      "GET /api/watchlist": watchlist,
      "POST /api/watchlist": { __status: 404, error: { code: "symbol_not_found", message: "no market data found for NOPE.NS" } },
    });
    renderAt(<WatchlistPage />);
    await userEvent.type(screen.getByLabelText("Symbol"), "NOPE");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no market data found for NOPE.NS");
  });

  it("removes a symbol", async () => {
    let list = [...watchlist];
    const calls = mockApi({
      "GET /api/watchlist": () => list,
      "DELETE /api/watchlist/": () => {
        list = list.filter((w) => w.symbol !== "TCS.NS");
        return undefined;
      },
    });
    renderAt(<WatchlistPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove TCS.NS" }));
    await waitFor(() => expect(screen.queryByText("TCS.NS")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("TCS.NS"))).toBe(true);
  });

  it("searches and adds from results", async () => {
    const calls = mockApi({
      "GET /api/watchlist": watchlist,
      "GET /api/stocks/search": [{ symbol: "INFY.NS", name: "Infosys", exchange: "NSE" }],
      "POST /api/watchlist": { symbol: "INFY.NS", exchange: "NSE", name: "Infosys", notify_signals: true },
    });
    renderAt(<WatchlistPage />);
    await userEvent.type(screen.getByLabelText("Search stocks"), "infos");
    await userEvent.click(await screen.findByRole("button", { name: "Add INFY.NS" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  });

  it("is accessible", async () => {
    mockApi({ "GET /api/watchlist": watchlist });
    const { container } = renderAt(<WatchlistPage />);
    await screen.findByText("RELIANCE.NS");
    expect(await axeViolations(container)).toEqual([]);
  });
});
