import { FreshnessBadge } from "../components/Badges";
import { useQuote } from "../hooks/queries";
import { istTime, money, pct } from "../services/format";

/** Table cells for one symbol's latest available quote: price, change, timestamp + freshness. */
export function QuoteCells({ symbol }: { symbol: string }) {
  const q = useQuote(symbol);
  if (q.isPending)
    return (
      <td colSpan={3} className="muted">
        Loading quote…
      </td>
    );
  if (q.isError)
    return (
      <td colSpan={3} className="neg">
        Quote unavailable: {q.error.message}
      </td>
    );
  const d = q.data;
  const cls = d.change_pct == null ? "" : d.change_pct >= 0 ? "pos" : "neg";
  return (
    <>
      <td className="num">{money(d.price)}</td>
      <td className={`num ${cls}`}>{pct(d.change_pct)}</td>
      <td>
        <FreshnessBadge value={d.freshness} /> <span className="muted small">{istTime(d.data_timestamp)}</span>
      </td>
    </>
  );
}
