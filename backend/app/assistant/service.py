"""Grounded assistant. The deterministic engine owns every number; the LLM only rephrases supplied facts."""

import json
import re

from app.assistant.ollama import OllamaClient, OllamaUnavailable

SYSTEM_PROMPT = """You are an educational assistant inside a personal stock-market dashboard for Indian equities.
Rules you must follow:
- Use ONLY the facts in the CONTEXT JSON. Never invent prices, indicator values, news, headlines or events.
- If a value is missing, null, stale or cached, say so explicitly and mention its timestamp.
- Signals come from a deterministic rule engine. Explain its rules; do not create new signals or predictions.
- Never say a stock will rise or fall. Never guarantee returns. Remind that signals are educational, not advice.
- You cannot place trades. If asked to trade, explain that only simulated paper trades exist, entered manually.
- Quote data timestamps and freshness labels when you cite prices.
Be concise (under 200 words) and use plain language."""

GLOSSARY = {
    "rsi": "RSI(14) compares the size of recent gains to recent losses on a 0-100 scale. Above ~70 is often "
    "called overbought, below ~30 oversold. It measures momentum, not value, and can stay extreme for long.",
    "macd": "MACD is EMA(12) minus EMA(26). Its 9-period EMA is the signal line; the histogram is the gap "
    "between them. It shows trend momentum and lags price.",
    "moving average": "A simple moving average (SMA) is the plain mean of the last N closes; an exponential "
    "moving average (EMA) weights recent closes more. Price above a rising average is often "
    "read as an uptrend. Averages lag price by design.",
    "atr": "ATR(14) is the average true range: typical daily movement including gaps. This app uses it to place "
    "stop-losses (entry minus 2 x ATR by default) so stops scale with volatility.",
}

TRADE_INTENT = re.compile(r"\b(place|execute|submit|put)\b.*\b(order|trade)\b|\b(buy|sell)\s+\d+", re.I)


def detect_symbols(message: str, known: list[str]) -> list[str]:
    text = message.upper()
    return [s for s in known if s in text or re.search(rf"\b{re.escape(s.split('.')[0])}\b", text)]


def deterministic_answer(message: str, context: dict) -> str:
    """Template answer built only from engine output. Always available, no LLM required."""
    parts: list[str] = []
    lower = message.lower()
    for term, text in GLOSSARY.items():
        if term in lower or (term == "moving average" and re.search(r"\b(sma|ema)\b", lower)):
            parts.append(text)
    for s in context.get("signals", []):
        line = (
            f"{s['symbol']}: latest signal {s['signal_type']} (strategy {s['strategy_version']}) "
            f"at {fmt_price(s['price'])}, data {s['data_timestamp'] or 'unknown'} [{s['freshness']}]."
        )
        if s["rules_triggered"]:
            line += " Rules met: " + "; ".join(s["rules_triggered"]) + "."
        if s["rules_failed"]:
            line += " Not met / blocking: " + "; ".join(s["rules_failed"]) + "."
        risk = s.get("risk") or {}
        if risk.get("stop_loss"):
            line += f" Risk levels: stop {risk['stop_loss']}, target {risk['take_profit']}, ATR(14) {risk['atr_14']}."
        if s["invalidation"]:
            line += " Invalidated if: " + "; ".join(s["invalidation"]) + "."
        parts.append(line)
    for q in context.get("quotes", []):
        if q.get("error"):
            parts.append(f"{q['symbol']}: no quote available ({q['error']}).")
        else:
            chg = f"{q['change_pct']:+.2f}%" if q.get("change_pct") is not None else "change n/a"
            parts.append(
                f"{q['symbol']}: {fmt_price(q['price'])} ({chg}) at {q['data_timestamp']} "
                f"[{q['freshness']}, via {q['provider']}]."
            )
    if not parts:
        parts.append(
            "No stored signals or quotes matched your question. Add symbols to the watchlist and run a "
            "refresh, or ask about RSI, MACD, moving averages or ATR."
        )
    parts.append("Signals are educational rule outputs, not advice or predictions.")
    return "\n".join(parts)


def fmt_price(p: float | None) -> str:
    return f"INR {p:,.2f}" if p is not None else "price unavailable"


def answer(message: str, context: dict, llm: OllamaClient | None) -> dict:
    if TRADE_INTENT.search(message):
        return {
            "answer": "I can't place or execute trades. This app only records simulated paper trades that you "
            "enter yourself on the Paper Portfolio page.",
            "llm_used": False,
            "refused": True,
            "context": context,
        }
    fallback = deterministic_answer(message, context)
    if llm is None:
        return {"answer": fallback, "llm_used": False, "llm_error": "Ollama not configured", "context": context}
    try:
        prompt = f"CONTEXT JSON:\n{json.dumps(context, default=str)}\n\nQUESTION: {message}"
        text = llm.chat(SYSTEM_PROMPT, prompt)
        return {
            "answer": text,
            "llm_used": True,
            "model": llm.model,
            "deterministic_answer": fallback,
            "context": context,
        }
    except OllamaUnavailable as e:
        return {"answer": fallback, "llm_used": False, "llm_error": f"Ollama unavailable ({e})", "context": context}
