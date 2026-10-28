import { Link } from "react-router";

import { SignalBadge } from "../components/Badges";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { Tilt3D } from "../components/Tilt3D";
import { QuoteCells } from "../features/QuoteCells";
import { useLatestSignals, usePortfolio, useProviders, useRefreshSignals, useWatchlist } from "../hooks/queries";
import { istTime, money, pct } from "../services/format";

export function DashboardPage() {
  const watchlist = useWatchlist();
  const signals = useLatestSignals();
  const refresh = useRefreshSignals();
  const bySymbol = new Map((signals.data ?? []).map((s) => [s.symbol, s]));

  return (
    <div className="stack">
      <div className="row between wrap">
        <h1>Dashboard</h1>
        <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? "Refreshing…" : "Refresh data & signals"}
        </button>
      </div>
      {refresh.isError && <ErrorBox error={refresh.error} title="Refresh failed" />}
      <ProviderSummary />
      <section className="card" aria-labelledby="wl-h">
        <h2 id="wl-h">Watchlist</h2>
        {watchlist.isPending ? (
          <Loading label="Loading watchlist…" />
        ) : watchlist.isError ? (
          <ErrorBox error={watchlist.error} title="Could not load watchlist" />
        ) : watchlist.data.length === 0 ? (
          <Empty>
            Your watchlist is empty. <Link to="/watchlist">Add Indian stocks</Link> such as RELIANCE.NS or TCS.NS.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Symbol</th>
                  <th scope="col" className="num">
                    Latest price
                  </th>
                  <th scope="col" className="num">
                    Change
                  </th>
                  <th scope="col">Data</th>
                  <th scope="col">Signal</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.data.map((w) => {
                  const s = bySymbol.get(w.symbol);
                  return (
                    <tr key={w.symbol}>
                      <th scope="row">
                        <Link to={`/stocks/${w.symbol}`}>{w.symbol}</Link>
                        <div className="muted small">
                          {w.name ?? ""} · {w.exchange}
                        </div>
                      </th>
                      <QuoteCells symbol={w.symbol} />
                      <td>
                        {s ? (
                          <>
                            <SignalBadge type={s.signal_type} />
                            <div className="muted small">bar {istTime(s.data_timestamp)}</div>
                          </>
                        ) : (
                          <span className="muted">Not evaluated yet</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <PortfolioSummary />
    </div>
  );
}

function ProviderSummary() {
  const p = useProviders();
  if (p.isPending) return <Loading label="Checking data providers…" />;
  if (p.isError) return <ErrorBox error={p.error} title="Provider status unavailable" />;
  const configured = p.data.providers.filter((x) => x.configured);
  return (
    <section className="card" aria-labelledby="prov-h">
      <h2 id="prov-h">Market data</h2>
      <p className="row gap wrap">
        {configured.map((x) => (
          <span key={x.name} className={`badge ${x.last_error ? "fresh-stale" : "fresh-delayed"}`}>
            {x.name}
            {x.last_error ? ": error" : ""}
          </span>
        ))}
        <span className="muted small">
          Last scheduled run: {p.data.scheduler.last_run.finished_at ? istTime(p.data.scheduler.last_run.finished_at) : "not yet"}
        </span>
      </p>
      {!p.data.live_data_available && <p className="muted small">{p.data.note}</p>}
    </section>
  );
}

function PortfolioSummary() {
  const p = usePortfolio();
  return (
    <section className="card" aria-labelledby="pf-h">
      <h2 id="pf-h">
        Paper portfolio <span className="pill">simulated</span>
      </h2>
      {p.isPending ? (
        <Loading />
      ) : p.isError ? (
        <ErrorBox error={p.error} />
      ) : (
        <dl className="kpis">
          <Tilt3D>
            <dt>Equity</dt>
            <dd>{money(p.data.equity)}</dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Cash</dt>
            <dd>{money(p.data.cash)}</dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Unrealized P&L</dt>
            <dd className={p.data.unrealized_pnl >= 0 ? "pos" : "neg"}>{money(p.data.unrealized_pnl)}</dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Realized P&L</dt>
            <dd className={p.data.realized_pnl >= 0 ? "pos" : "neg"}>{money(p.data.realized_pnl)}</dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Exposure</dt>
            <dd>{pct(p.data.exposure_pct).replace("+", "")}</dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Open positions</dt>
            <dd>{p.data.positions.length}</dd>
          </Tilt3D>
        </dl>
      )}
    </section>
  );
}
