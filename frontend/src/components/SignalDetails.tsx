import { istTime, money } from "../services/format";
import type { Signal } from "../types/api";
import { FreshnessBadge, SignalBadge } from "./Badges";

export function SignalDetails({ signal }: { signal: Signal }) {
  const r = signal.risk ?? {};
  return (
    <article className="card signal" aria-label={`${signal.signal_type} signal for ${signal.symbol}`}>
      <header className="row between">
        <div className="row gap">
          <SignalBadge type={signal.signal_type} />
          <strong>
            {signal.symbol} <span className="muted">({signal.exchange})</span>
          </strong>
        </div>
        <FreshnessBadge value={signal.freshness} />
      </header>
      <dl className="facts">
        <div>
          <dt>Price at evaluation</dt>
          <dd>{money(signal.price)}</dd>
        </div>
        <div>
          <dt>Data timestamp</dt>
          <dd>
            {istTime(signal.data_timestamp)} {signal.provider && <span className="muted">via {signal.provider}</span>}
          </dd>
        </div>
        <div>
          <dt>Evaluated</dt>
          <dd>{istTime(signal.signal_timestamp)}</dd>
        </div>
        <div>
          <dt>Strategy</dt>
          <dd>{signal.strategy_version}</dd>
        </div>
      </dl>
      {signal.rules_triggered.length > 0 && (
        <section>
          <h3 className="label">Rules met</h3>
          <ul className="rules ok">
            {signal.rules_triggered.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </section>
      )}
      {signal.rules_failed.length > 0 && (
        <section>
          <h3 className="label">Not met / blocking</h3>
          <ul className="rules fail">
            {signal.rules_failed.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </section>
      )}
      {(r.stop_loss || signal.invalidation.length > 0) && (
        <section aria-label="Risk">
          <h3 className="label">Risk</h3>
          {r.stop_loss != null && (
            <p>
              Stop-loss <strong>{money(r.stop_loss)}</strong> · Take-profit <strong>{money(r.take_profit)}</strong> ·
              Risk/share {money(r.risk_per_share)} · ATR(14) {r.atr_14 ?? "—"}
            </p>
          )}
          {signal.invalidation.length > 0 && <p>Invalidated if: {signal.invalidation.join("; ")}.</p>}
        </section>
      )}
      <p className="disclaimer">Educational rule output, not investment advice. A signal does not mean the price will move.</p>
    </article>
  );
}
