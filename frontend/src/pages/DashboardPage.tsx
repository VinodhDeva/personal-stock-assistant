import { motion } from "motion/react";
import { Link } from "react-router";

import { AnimatedNumber } from "../components/AnimatedNumber";
import { SignalBadge } from "../components/Badges";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { Tilt3D } from "../components/Tilt3D";
import { QuoteCells } from "../features/QuoteCells";
import { useLatestSignals, usePortfolio, useProviders, useRefreshSignals, useWatchlist } from "../hooks/queries";
import { istTime, money } from "../services/format";

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
                {watchlist.data.map((w, i) => {
                  const s = bySymbol.get(w.symbol);
                  return (
                    <motion.tr
                      key={w.symbol}
                      initial={{ opacity: 0, x: -12 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ type: "spring", bounce: 0.2, duration: 0.5, delay: i * 0.06 }}
                    >
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
                    </motion.tr>
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
            <dd>
              <AnimatedNumber from={0} value={p.data.equity} format={money} />
            </dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Cash</dt>
            <dd>
              <AnimatedNumber from={0} value={p.data.cash} format={money} />
            </dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Unrealized P&L</dt>
            <dd className={p.data.unrealized_pnl >= 0 ? "pos" : "neg"}><AnimatedNumber from={0} value={p.data.unrealized_pnl} format={money} />
            </dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Realized P&L</dt>
            <dd className={p.data.realized_pnl >= 0 ? "pos" : "neg"}><AnimatedNumber from={0} value={p.data.realized_pnl} format={money} />
            </dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Exposure</dt>
            <dd>
              <AnimatedNumber from={0} value={p.data.exposure_pct} format={(v) => `${v.toFixed(2)}%`} />
            </dd>
          </Tilt3D>
          <Tilt3D>
            <dt>Open positions</dt>
            <dd>
              <AnimatedNumber from={0} value={p.data.positions.length} format={(v) => String(Math.round(v))} />
            </dd>
          </Tilt3D>
        </dl>
      )}
    </section>
  );
}
