import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useParams } from "react-router";

import { FreshnessBadge } from "../components/Badges";
import { MacdChart, PriceChart, RsiChart } from "../components/Charts";
import { SignalDetails } from "../components/SignalDetails";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useAlerts, useBacktest, useHistory, useIndicators, useQuote, useSignals } from "../hooks/queries";
import { del, post } from "../services/api";
import { istTime, money, number, pct } from "../services/format";

const PERIODS = ["3mo", "6mo", "1y", "2y"] as const;

export function StockDetailPage() {
  const { symbol = "" } = useParams();
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("1y");
  const quote = useQuote(symbol);
  const history = useHistory(symbol, period);
  const ind = useIndicators(symbol, period);
  const signals = useSignals(symbol, 10);
  const qc = useQueryClient();
  const evaluate = useMutation({
    mutationFn: () => post(`/api/signals/${encodeURIComponent(symbol)}/evaluate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });

  return (
    <div className="stack">
      <div className="row between wrap">
        <h1>{symbol}</h1>
        {quote.data && (
          <div className="quote-head">
            <span className="big">{money(quote.data.price)}</span>{" "}
            <span className={(quote.data.change_pct ?? 0) >= 0 ? "pos" : "neg"}>{pct(quote.data.change_pct)}</span>{" "}
            <FreshnessBadge value={quote.data.freshness} />
            <div className="muted small">
              {quote.data.exchange} · data {istTime(quote.data.data_timestamp)} · via {quote.data.provider}
            </div>
            {quote.data.warnings.map((w) => (
              <p key={w} className="warn small">
                {w}
              </p>
            ))}
          </div>
        )}
        {quote.isError && <ErrorBox error={quote.error} title="Quote unavailable" />}
      </div>

      <section className="card" aria-labelledby="chart-h">
        <div className="row between wrap">
          <h2 id="chart-h">Price history (daily)</h2>
          <div role="group" aria-label="Chart period" className="row gap">
            {PERIODS.map((p) => (
              <button key={p} className={p === period ? "" : "secondary"} aria-pressed={p === period} onClick={() => setPeriod(p)}>
                {p}
              </button>
            ))}
          </div>
        </div>
        {history.isPending || ind.isPending ? (
          <Loading label="Loading chart…" />
        ) : history.isError ? (
          <ErrorBox error={history.error} title="History unavailable" />
        ) : ind.isError ? (
          <ErrorBox error={ind.error} />
        ) : history.data.candles.length === 0 ? (
          <Empty>No historical data.</Empty>
        ) : (
          <>
            <p className="muted small">
              <FreshnessBadge value={history.data.freshness} /> last bar {istTime(history.data.data_timestamp)} · via{" "}
              {history.data.provider}
            </p>
            <PriceChart candles={history.data.candles} indicators={ind.data.series} />
            <h3>RSI (14)</h3>
            <RsiChart indicators={ind.data.series} />
            <h3>MACD (12, 26, 9)</h3>
            <MacdChart indicators={ind.data.series} />
            {ind.data.latest && <LatestIndicators latest={ind.data.latest} />}
          </>
        )}
      </section>

      <section className="card" aria-labelledby="sig-h">
        <div className="row between wrap">
          <h2 id="sig-h">Recent signals & explanations</h2>
          <button className="secondary" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
            {evaluate.isPending ? "Evaluating…" : "Evaluate now"}
          </button>
        </div>
        {evaluate.isError && <ErrorBox error={evaluate.error} />}
        {signals.isPending ? (
          <Loading />
        ) : signals.isError ? (
          <ErrorBox error={signals.error} />
        ) : signals.data.items.length === 0 ? (
          <Empty>No signals recorded yet. Click “Evaluate now”.</Empty>
        ) : (
          <div className="stack">
            {signals.data.items.map((s) => (
              <SignalDetails key={s.id} signal={s} />
            ))}
          </div>
        )}
      </section>

      <AlertsSection symbol={symbol} />
      <BacktestSection symbol={symbol} />
    </div>
  );
}

function LatestIndicators({ latest }: { latest: NonNullable<ReturnType<typeof useIndicators>["data"]>["latest"] }) {
  if (!latest) return null;
  const rows: [string, number | null][] = [
    ["RSI 14", latest.rsi_14],
    ["SMA 20", latest.sma_20],
    ["SMA 50", latest.sma_50],
    ["EMA 12", latest.ema_12],
    ["EMA 26", latest.ema_26],
    ["MACD", latest.macd],
    ["MACD signal", latest.macd_signal],
    ["ATR 14", latest.atr_14],
    ["Avg volume 20", latest.avg_volume_20],
    ["% change", latest.pct_change],
  ];
  return (
    <dl className="kpis small-kpis" aria-label="Latest indicator values">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{number(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function AlertsSection({ symbol }: { symbol: string }) {
  const alerts = useAlerts(symbol);
  const qc = useQueryClient();
  const [condition, setCondition] = useState<"above" | "below">("above");
  const [price, setPrice] = useState("");
  const create = useMutation({
    mutationFn: () => post("/api/alerts", { symbol, condition, price: Number(price) }),
    onSuccess: () => {
      setPrice("");
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/alerts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  return (
    <section className="card" aria-labelledby="alert-h">
      <h2 id="alert-h">Price alerts</h2>
      <form onSubmit={submit} className="row gap wrap">
        <label>
          Condition
          <select value={condition} onChange={(e) => setCondition(e.target.value as "above" | "below")}>
            <option value="above">Price at or above</option>
            <option value="below">Price at or below</option>
          </select>
        </label>
        <label>
          Price (INR)
          <input type="number" min="0.01" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} required />
        </label>
        <button type="submit" disabled={create.isPending}>
          Add alert
        </button>
      </form>
      {create.isError && <ErrorBox error={create.error} />}
      {alerts.data && alerts.data.length > 0 ? (
        <ul className="results">
          {alerts.data.map((a) => (
            <li key={a.id} className="row between wrap">
              <span>
                {a.condition} {money(a.price)}{" "}
                {a.active ? (
                  <span className="badge fresh-delayed">active</span>
                ) : (
                  <span className="badge fresh-cached">
                    triggered {istTime(a.triggered_at)} at {money(a.triggered_price)}
                  </span>
                )}
              </span>
              <button className="danger" onClick={() => remove.mutate(a.id)} aria-label={`Delete alert ${a.condition} ${a.price}`}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">No alerts. Alerts are checked by the scheduler during market hours (one-shot).</p>
      )}
    </section>
  );
}

function BacktestSection({ symbol }: { symbol: string }) {
  const [run, setRun] = useState(false);
  const bt = useBacktest(symbol, run);
  return (
    <section className="card" aria-labelledby="bt-h">
      <div className="row between wrap">
        <h2 id="bt-h">Hypothetical backtest (2y, daily)</h2>
        <button className="secondary" onClick={() => (run ? bt.refetch() : setRun(true))} disabled={bt.isFetching}>
          {bt.isFetching ? "Running…" : "Run backtest"}
        </button>
      </div>
      {bt.isError && <ErrorBox error={bt.error} />}
      {bt.data && (
        <>
          <dl className="kpis">
            <div>
              <dt>Strategy return</dt>
              <dd className={bt.data.total_return_pct >= 0 ? "pos" : "neg"}>{pct(bt.data.total_return_pct)}</dd>
            </div>
            <div>
              <dt>Buy & hold</dt>
              <dd>{pct(bt.data.buy_and_hold_return_pct)}</dd>
            </div>
            <div>
              <dt>Max drawdown</dt>
              <dd>{pct(-bt.data.max_drawdown_pct)}</dd>
            </div>
            <div>
              <dt>Trades</dt>
              <dd>{bt.data.num_trades}</dd>
            </div>
            <div>
              <dt>Win rate</dt>
              <dd>{bt.data.win_rate_pct == null ? "—" : `${bt.data.win_rate_pct}%`}</dd>
            </div>
            <div>
              <dt>Costs paid</dt>
              <dd>{money(bt.data.total_costs)}</dd>
            </div>
          </dl>
          <p className="muted small">
            {bt.data.bars} bars via {bt.data.provider} ({bt.data.freshness}). Signals on completed bar close, filled next open,{" "}
            {bt.data.assumptions.cost_bps_per_side} bps cost + {bt.data.assumptions.slippage_bps_per_side} bps slippage per side.{" "}
            {bt.data.assumptions.disclaimer}
          </p>
        </>
      )}
    </section>
  );
}
