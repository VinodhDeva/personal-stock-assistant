import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Empty, ErrorBox, Loading } from "../components/Status";
import { useProviders, useSettings } from "../hooks/queries";
import { put } from "../services/api";
import { istTime } from "../services/format";
import type { StrategyConfig } from "../types/api";

export function SettingsPage() {
  return (
    <div className="stack">
      <h1>Settings</h1>
      <StatusPanel />
      <StrategyForm />
    </div>
  );
}

function StatusPanel() {
  const p = useProviders();
  if (p.isPending) return <Loading label="Checking providers, Ollama and Telegram…" />;
  if (p.isError) return <ErrorBox error={p.error} />;
  const d = p.data;
  return (
    <>
      <section className="card" aria-labelledby="prov-h">
        <h2 id="prov-h">Data providers</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Provider</th>
                <th scope="col">Configured</th>
                <th scope="col">Capabilities</th>
                <th scope="col">Notes</th>
              </tr>
            </thead>
            <tbody>
              {d.providers.map((x) => (
                <tr key={x.name}>
                  <th scope="row">{x.name}</th>
                  <td>{x.configured ? "Yes" : "No"}</td>
                  <td className="small">
                    {Object.entries(x.capabilities)
                      .filter(([, v]) => v === true)
                      .map(([k]) => k)
                      .join(", ") || "—"}
                  </td>
                  <td className="small">
                    {String(x.capabilities.notes ?? "")}
                    {x.last_error && <div className="neg">Last error: {x.last_error}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">{d.note}</p>
      </section>
      <section className="card" aria-labelledby="svc-h">
        <h2 id="svc-h">Services</h2>
        <dl className="facts">
          <div>
            <dt>Ollama</dt>
            <dd>
              {d.ollama.reachable
                ? d.ollama.model_available
                  ? `Connected · model ${d.ollama.model}`
                  : `Reachable, but model ${d.ollama.model} is not installed (run: ollama pull ${d.ollama.model})`
                : "Not reachable. Explanations fall back to deterministic text."}
            </dd>
          </div>
          <div>
            <dt>Telegram</dt>
            <dd>{d.telegram.configured ? "Configured" : d.telegram.help}</dd>
          </div>
          <div>
            <dt>Scheduler</dt>
            <dd>
              {d.scheduler.enabled ? "Enabled" : "Disabled"} · market hours {d.scheduler.market_open.slice(0, 5)}–
              {d.scheduler.market_close.slice(0, 5)} {d.scheduler.market_timezone} · last run{" "}
              {d.scheduler.last_run.finished_at ? istTime(d.scheduler.last_run.finished_at) : "not yet"}
            </dd>
          </div>
        </dl>
      </section>
    </>
  );
}

const FIELDS: { key: keyof StrategyConfig; label: string; step?: string }[] = [
  { key: "rsi_buy_min", label: "RSI minimum for BUY" },
  { key: "rsi_buy_max", label: "RSI maximum for BUY (overbought)" },
  { key: "volume_multiplier", label: "Volume ≥ × 20-day average", step: "0.1" },
  { key: "atr_stop_multiplier", label: "Stop-loss = entry − k × ATR", step: "0.1" },
  { key: "reward_risk_ratio", label: "Take-profit reward:risk", step: "0.1" },
  { key: "max_risk_per_trade_pct", label: "Max risk per trade (% equity)", step: "0.1" },
  { key: "max_portfolio_exposure_pct", label: "Max portfolio exposure (%)" },
];

function StrategyForm() {
  const s = useSettings();
  const qc = useQueryClient();
  const [cfg, setCfg] = useState<StrategyConfig | null>(null);
  const [interval, setIntervalSec] = useState(300);
  useEffect(() => {
    if (s.data) {
      setCfg(s.data.strategy);
      setIntervalSec(s.data.refresh_interval_seconds);
    }
  }, [s.data]);
  const save = useMutation({
    mutationFn: async () => {
      await put("/api/settings/strategy", cfg);
      await put("/api/settings/scheduler", { refresh_interval_seconds: interval });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  if (s.isPending) return <Loading />;
  if (s.isError) return <ErrorBox error={s.error} />;
  if (!cfg) return <Empty>No settings.</Empty>;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <section className="card" aria-labelledby="strat-h">
      <h2 id="strat-h">Strategy thresholds (ema_crossover_v1)</h2>
      <p className="muted small">Example rules for education, not a proven strategy. Changes apply to the next evaluation.</p>
      <form onSubmit={submit} className="grid-form">
        {FIELDS.map((f) => (
          <label key={f.key}>
            {f.label}
            <input
              type="number"
              step={f.step ?? "1"}
              value={cfg[f.key] as number}
              onChange={(e) => setCfg({ ...cfg, [f.key]: Number(e.target.value) })}
              required
            />
          </label>
        ))}
        <label className="inline">
          <input
            type="checkbox"
            checked={cfg.require_rsi_rising}
            onChange={(e) => setCfg({ ...cfg, require_rsi_rising: e.target.checked })}
          />
          Require RSI rising
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={cfg.require_close_above_sma20}
            onChange={(e) => setCfg({ ...cfg, require_close_above_sma20: e.target.checked })}
          />
          Require close above SMA20
        </label>
        <label>
          Refresh interval (seconds, min 60)
          <input type="number" min="60" step="60" value={interval} onChange={(e) => setIntervalSec(Number(e.target.value))} />
        </label>
        <div className="row gap end">
          <button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
      {save.isError && <ErrorBox error={save.error} title="Not saved" />}
      {save.isSuccess && <p className="pos">Saved.</p>}
      <p className="muted small">
        A shorter interval cannot make free data fresher than the provider publishes it. Stale data after{" "}
        {s.data.stale_after_minutes} min during market hours; notification cooldown {s.data.notification_cooldown_minutes} min.
      </p>
    </section>
  );
}
