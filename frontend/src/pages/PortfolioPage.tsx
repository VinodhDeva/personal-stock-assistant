import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { FreshnessBadge } from "../components/Badges";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { usePortfolio, useTrades } from "../hooks/queries";
import { post } from "../services/api";
import { istTime, money, number } from "../services/format";

const opt = (v: string) => (v.trim() === "" ? undefined : Number(v));

export function PortfolioPage() {
  const p = usePortfolio();
  const trades = useTrades();
  return (
    <div className="stack">
      <h1>
        Paper portfolio <span className="pill">simulated, no real orders</span>
      </h1>
      {p.isPending ? (
        <Loading />
      ) : p.isError ? (
        <ErrorBox error={p.error} />
      ) : (
        <>
          <section className="card">
            <dl className="kpis">
              <div>
                <dt>Equity</dt>
                <dd>{money(p.data.equity)}</dd>
              </div>
              <div>
                <dt>Cash</dt>
                <dd>{money(p.data.cash)}</dd>
              </div>
              <div>
                <dt>Unrealized P&L</dt>
                <dd className={p.data.unrealized_pnl >= 0 ? "pos" : "neg"}>{money(p.data.unrealized_pnl)}</dd>
              </div>
              <div>
                <dt>Realized P&L</dt>
                <dd className={p.data.realized_pnl >= 0 ? "pos" : "neg"}>{money(p.data.realized_pnl)}</dd>
              </div>
              <div>
                <dt>Exposure</dt>
                <dd>{p.data.exposure_pct}%</dd>
              </div>
              <div>
                <dt>Max drawdown</dt>
                <dd>{p.data.max_drawdown_pct}%</dd>
              </div>
            </dl>
            <p className="muted small">
              Starting capital {money(p.data.starting_capital)} · fees paid {money(p.data.total_fees)}
            </p>
          </section>
          <section className="card" aria-labelledby="pos-h">
            <h2 id="pos-h">Positions</h2>
            {p.data.positions.length === 0 ? (
              <Empty>No open simulated positions.</Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Symbol</th>
                      <th scope="col" className="num">
                        Qty
                      </th>
                      <th scope="col" className="num">
                        Avg entry
                      </th>
                      <th scope="col" className="num">
                        Current
                      </th>
                      <th scope="col" className="num">
                        Unrealized
                      </th>
                      <th scope="col" className="num">
                        Exposure
                      </th>
                      <th scope="col">Stop / target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.data.positions.map((x) => (
                      <tr key={x.symbol}>
                        <th scope="row">
                          <Link to={`/stocks/${x.symbol}`}>{x.symbol}</Link>
                        </th>
                        <td className="num">{number(x.quantity)}</td>
                        <td className="num">{money(x.avg_price)}</td>
                        <td className="num">
                          {x.price_available ? money(x.current_price) : <span className="neg">unavailable</span>}
                          {x.price_meta?.freshness && (
                            <div>
                              <FreshnessBadge value={x.price_meta.freshness} />
                            </div>
                          )}
                        </td>
                        <td className={`num ${(x.unrealized_pnl ?? 0) >= 0 ? "pos" : "neg"}`}>{money(x.unrealized_pnl)}</td>
                        <td className="num">{x.exposure_pct}%</td>
                        <td>
                          {money(x.stop_loss)} / {money(x.take_profit)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
      <TradeForm />
      <section className="card" aria-labelledby="hist-h">
        <h2 id="hist-h">Simulated trade history</h2>
        {trades.isPending ? (
          <Loading />
        ) : trades.isError ? (
          <ErrorBox error={trades.error} />
        ) : trades.data.items.length === 0 ? (
          <Empty>No simulated trades yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Symbol</th>
                  <th scope="col">Side</th>
                  <th scope="col" className="num">
                    Qty
                  </th>
                  <th scope="col" className="num">
                    Price
                  </th>
                  <th scope="col" className="num">
                    Realized
                  </th>
                  <th scope="col">Reason / price source</th>
                </tr>
              </thead>
              <tbody>
                {trades.data.items.map((t) => (
                  <tr key={t.id}>
                    <td>{istTime(t.executed_at)}</td>
                    <td>{t.symbol}</td>
                    <td>{t.side}</td>
                    <td className="num">{number(t.quantity)}</td>
                    <td className="num">{money(t.price)}</td>
                    <td className={`num ${(t.realized_pnl ?? 0) >= 0 ? "pos" : "neg"}`}>{money(t.realized_pnl)}</td>
                    <td className="small">
                      {t.reason ?? "—"}
                      <div className="muted">{t.price_source}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function TradeForm() {
  const qc = useQueryClient();
  const [f, setF] = useState({ symbol: "", side: "BUY", quantity: "", price: "", stop_loss: "", take_profit: "", fees: "" });
  const [entry, setEntry] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const trade = useMutation({
    mutationFn: () =>
      post("/api/portfolio/paper-trades", {
        symbol: f.symbol.trim(),
        side: f.side,
        quantity: Number(f.quantity),
        price: opt(f.price),
        stop_loss: opt(f.stop_loss),
        take_profit: opt(f.take_profit),
        fees: opt(f.fees) ?? 0,
        reason: "manual paper trade",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }).then(() => qc.invalidateQueries({ queryKey: ["trades"] })),
  });
  const sizer = useMutation({
    mutationFn: () =>
      post<{ quantity: number; risk_budget: number; risk_amount: number | null }>("/api/portfolio/position-size", {
        entry: Number(entry || f.price),
        stop_loss: opt(f.stop_loss),
      }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    trade.mutate();
  };
  return (
    <section className="card" aria-labelledby="trade-h">
      <h2 id="trade-h">Record a simulated trade</h2>
      <form onSubmit={submit} className="grid-form">
        <label>
          Symbol
          <input value={f.symbol} onChange={set("symbol")} placeholder="INFY.NS" required />
        </label>
        <label>
          Side
          <select value={f.side} onChange={set("side")}>
            <option>BUY</option>
            <option>SELL</option>
          </select>
        </label>
        <label>
          Quantity
          <input type="number" min="1" step="1" value={f.quantity} onChange={set("quantity")} required />
        </label>
        <label>
          Price (blank = latest available)
          <input type="number" min="0.01" step="0.01" value={f.price} onChange={set("price")} />
        </label>
        <label>
          Stop-loss
          <input type="number" min="0.01" step="0.01" value={f.stop_loss} onChange={set("stop_loss")} />
        </label>
        <label>
          Take-profit
          <input type="number" min="0.01" step="0.01" value={f.take_profit} onChange={set("take_profit")} />
        </label>
        <label>
          Fees
          <input type="number" min="0" step="0.01" value={f.fees} onChange={set("fees")} />
        </label>
        <div className="row gap end">
          <button type="submit" disabled={trade.isPending}>
            Record paper trade
          </button>
        </div>
      </form>
      {trade.isError && <ErrorBox error={trade.error} title="Trade rejected" />}
      {trade.isSuccess && <p className="pos">Simulated trade recorded.</p>}
      <div className="row gap wrap sizer">
        <label>
          Entry for sizing
          <input type="number" min="0.01" step="0.01" value={entry} onChange={(e) => setEntry(e.target.value)} />
        </label>
        <button className="secondary" type="button" onClick={() => sizer.mutate()} disabled={!(entry || f.price)}>
          Suggest position size
        </button>
        {sizer.data && (
          <span>
            Max {sizer.data.quantity} shares (risk budget {money(sizer.data.risk_budget)}
            {sizer.data.risk_amount != null && `, risk ${money(sizer.data.risk_amount)}`})
          </span>
        )}
        {sizer.isError && <ErrorBox error={sizer.error} />}
      </div>
    </section>
  );
}
