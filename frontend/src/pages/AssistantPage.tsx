import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { FreshnessBadge } from "../components/Badges";
import { ErrorBox } from "../components/Status";
import { post } from "../services/api";
import { istTime, money } from "../services/format";
import type { ChatResponse } from "../types/api";

const EXAMPLES = [
  "Which watchlist stocks currently meet my configured conditions?",
  "What are the main risks associated with the latest signals?",
  "Summarize today's recorded market movements.",
  "Explain RSI, MACD, moving averages and ATR.",
];

interface Turn {
  q: string;
  a?: ChatResponse;
}

export function AssistantPage() {
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const chat = useMutation({
    mutationFn: (q: string) => post<ChatResponse>("/api/assistant/chat", { message: q }),
    onSuccess: (a, q) => setTurns((t) => t.map((x) => (x.q === q && !x.a ? { ...x, a } : x))),
  });
  const ask = (q: string) => {
    if (!q.trim() || chat.isPending) return;
    setTurns((t) => [...t, { q }]);
    setMessage("");
    chat.mutate(q);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(message);
  };

  return (
    <div className="stack">
      <h1>AI Assistant</h1>
      <p className="muted">
        Answers are grounded in the backend's stored signals and quotes. The local LLM (Ollama) only explains them; it cannot
        create signals or place trades. If Ollama is offline you get the deterministic explanation instead.
      </p>
      <div className="row gap wrap">
        {EXAMPLES.map((e) => (
          <button key={e} className="secondary small" onClick={() => ask(e)}>
            {e}
          </button>
        ))}
      </div>
      <section className="chat" aria-live="polite" aria-label="Conversation">
        {turns.map((t, i) => (
          <div key={i} className="stack">
            <div className="bubble user">{t.q}</div>
            {t.a ? <Answer a={t.a} /> : <div className="bubble bot muted">Thinking… (local models can take ~30s)</div>}
          </div>
        ))}
      </section>
      {chat.isError && <ErrorBox error={chat.error} />}
      <form onSubmit={submit} className="row gap">
        <label className="grow">
          <span className="sr-only">Your question</span>
          <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Why did TCS generate a HOLD?" />
        </label>
        <button type="submit" disabled={chat.isPending}>
          Ask
        </button>
      </form>
    </div>
  );
}

function Answer({ a }: { a: ChatResponse }) {
  return (
    <div className="bubble bot">
      <p className="muted small">
        {a.refused
          ? "Trade request refused"
          : a.llm_used
            ? `Explained by local model ${a.model}`
            : `Deterministic explanation (${a.llm_error ?? "LLM not used"})`}{" "}
        · context as of {istTime(a.context.as_of)}
      </p>
      <div className="answer">{a.answer}</div>
      {a.context.quotes.length > 0 && (
        <details>
          <summary>Evidence used ({a.context.quotes.length} quotes, {a.context.signals.length} signals)</summary>
          <ul className="small">
            {a.context.quotes.map((q) => (
              <li key={q.symbol}>
                {q.symbol}:{" "}
                {q.error ? (
                  <span className="neg">{q.error}</span>
                ) : (
                  <>
                    {money(q.price)} at {istTime(q.data_timestamp)} {q.freshness && <FreshnessBadge value={q.freshness} />}
                  </>
                )}
              </li>
            ))}
            {a.context.signals.map((s) => (
              <li key={`s-${s.symbol}`}>
                {s.symbol}: {s.signal_type} on bar {istTime(s.data_timestamp)} ({s.strategy_version})
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
