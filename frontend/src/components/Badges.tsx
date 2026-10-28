import type { Freshness, SignalType } from "../types/api";

const FRESHNESS_HELP: Record<Freshness, string> = {
  live: "Provider confirmed real-time data",
  delayed: "Fresh response, but the provider does not guarantee real-time data",
  cached: "Served from cache or the last stored value after a failed fetch",
  historical: "Historical/end-of-day data (e.g. CSV upload)",
  stale: "Older than expected for current market hours; signals are not acted on",
};

export function FreshnessBadge({ value }: { value: Freshness }) {
  return (
    <span className={`badge fresh-${value}`} title={FRESHNESS_HELP[value]}>
      {value}
      <span className="sr-only"> data: {FRESHNESS_HELP[value]}</span>
    </span>
  );
}

export function SignalBadge({ type }: { type: SignalType }) {
  const label = type === "HOLD" ? "HOLD" : `Potential ${type}`;
  return <span className={`badge sig-${type.toLowerCase()}`}>{label}</span>;
}
