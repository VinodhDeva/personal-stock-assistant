import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Empty, ErrorBox, Loading } from "../components/Status";
import { useRemoveSymbol, useWatchlist } from "../hooks/queries";
import { api, post } from "../services/api";
import type { WatchlistItem } from "../types/api";

export function WatchlistPage() {
  const qc = useQueryClient();
  const watchlist = useWatchlist();
  const remove = useRemoveSymbol();
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [query, setQuery] = useState("");

  const add = useMutation({
    mutationFn: (s: string) => post<WatchlistItem>("/api/watchlist", { symbol: s, exchange }),
    onSuccess: () => {
      setSymbol("");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (w: WatchlistItem) =>
      api(`/api/watchlist/${encodeURIComponent(w.symbol)}`, {
        method: "PATCH",
        body: JSON.stringify({ notify_signals: !w.notify_signals }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const search = useQuery({
    queryKey: ["search", query],
    queryFn: () => api<{ symbol: string; name: string; exchange: string }[]>(`/api/stocks/search?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length >= 2,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (symbol.trim()) add.mutate(symbol.trim());
  };

  return (
    <div className="stack">
      <h1>Watchlist</h1>
      <section className="card" aria-labelledby="add-h">
        <h2 id="add-h">Add a symbol</h2>
        <form onSubmit={submit} className="row gap wrap">
          <label>
            Symbol
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="RELIANCE or RELIANCE.NS" required />
          </label>
          <label>
            Exchange
            <select value={exchange} onChange={(e) => setExchange(e.target.value as "NSE" | "BSE")}>
              <option value="NSE">NSE (.NS)</option>
              <option value="BSE">BSE (.BO)</option>
            </select>
          </label>
          <button type="submit" disabled={add.isPending}>
            {add.isPending ? "Validating…" : "Add"}
          </button>
        </form>
        {add.isError && <ErrorBox error={add.error} title="Could not add symbol" />}
        {add.data?.warning && <p className="warn">{add.data.warning}</p>}
        <label className="block">
          Search stocks
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. infosys, bank" />
        </label>
        {search.isFetching && <Loading label="Searching…" />}
        {search.data && search.data.length === 0 && <Empty>No matches.</Empty>}
        {search.data && search.data.length > 0 && (
          <ul className="results" aria-label="Search results">
            {search.data.map((r) => (
              <li key={r.symbol} className="row between">
                <span>
                  <strong>{r.symbol}</strong> <span className="muted">{r.name}</span>
                </span>
                <button className="secondary" onClick={() => add.mutate(r.symbol)} aria-label={`Add ${r.symbol}`}>
                  Add
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="list-h">
        <h2 id="list-h">Monitored symbols</h2>
        {watchlist.isPending ? (
          <Loading />
        ) : watchlist.isError ? (
          <ErrorBox error={watchlist.error} />
        ) : watchlist.data.length === 0 ? (
          <Empty>No symbols yet.</Empty>
        ) : (
          <ul className="results">
            {watchlist.data.map((w) => (
              <li key={w.symbol} className="row between wrap">
                <span>
                  <Link to={`/stocks/${w.symbol}`}>
                    <strong>{w.symbol}</strong>
                  </Link>{" "}
                  <span className="muted">
                    {w.name} · {w.exchange}
                  </span>
                </span>
                <span className="row gap">
                  <label className="inline">
                    <input type="checkbox" checked={w.notify_signals} onChange={() => toggle.mutate(w)} />
                    Signal alerts
                  </label>
                  <button className="danger" onClick={() => remove.mutate(w.symbol)} aria-label={`Remove ${w.symbol}`}>
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">
          Monitored conditions: the strategy thresholds on the <Link to="/settings">Settings</Link> page apply to all symbols. Price
          alerts are set per stock on its detail page.
        </p>
      </section>
    </div>
  );
}
