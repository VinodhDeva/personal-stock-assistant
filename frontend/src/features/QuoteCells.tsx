import { useAnimate } from "motion/react";
import { useEffect, useRef } from "react";

import { AnimatedNumber } from "../components/AnimatedNumber";
import { FreshnessBadge } from "../components/Badges";
import { useQuote } from "../hooks/queries";
import { istTime, money, pct } from "../services/format";

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Table cells for one symbol's latest available quote: price, change, timestamp + freshness. */
export function QuoteCells({ symbol }: { symbol: string }) {
  const q = useQuote(symbol);
  const price = q.data?.price;
  const prev = useRef<number | undefined>(undefined);
  const [scope, animate] = useAnimate<HTMLSpanElement>();

  // Flash green/red when a refetch brings a different price; never on first load.
  useEffect(() => {
    const before = prev.current;
    prev.current = price;
    if (before === undefined || price === undefined || before === price || !scope.current) return;
    const tint = cssVar(price > before ? "--up-soft" : "--down-soft");
    animate(scope.current, { backgroundColor: [tint, "rgba(0, 0, 0, 0)"] }, { duration: 1.2, ease: "easeOut" });
  }, [price, animate, scope]);

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
      <td className="num">
        <span ref={scope} className="flash">
          <AnimatedNumber value={d.price} format={money} />
        </span>
      </td>
      <td className={`num ${cls}`}>{pct(d.change_pct)}</td>
      <td>
        <FreshnessBadge value={d.freshness} /> <span className="muted small">{istTime(d.data_timestamp)}</span>
      </td>
    </>
  );
}
